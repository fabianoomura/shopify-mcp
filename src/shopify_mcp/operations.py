from __future__ import annotations

from datetime import datetime
import ipaddress
import json
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

from .client import ShopifyClient, ShopifyError, mutation_result
from .confirmations import ConfirmationManager
from .financial import check as check_financial, money as parse_money


def _page_size(value: Any) -> int:
    try:
        size = int(value or 25)
    except (TypeError, ValueError) as exc:
        raise ValueError("first deve ser inteiro") from exc
    if not 1 <= size <= 100:
        raise ValueError("first deve estar entre 1 e 100")
    return size


def _connection(data: dict[str, Any], key: str) -> dict[str, Any]:
    conn = data[key]
    return {
        "items": [edge["node"] for edge in conn.get("edges", [])],
        "pageInfo": conn.get("pageInfo", {}),
    }


def _search_exact(field: str, value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'{field}:"{escaped}"'


DISCOUNT_CODE_FRAGMENTS = """__typename ... on DiscountCodeBasic{title status startsAt endsAt summary asyncUsageCount codesCount{count} codes(first:20){nodes{id code}} combinesWith{orderDiscounts productDiscounts shippingDiscounts} appliesOncePerCustomer usageLimit} ... on DiscountCodeBxgy{title status startsAt endsAt summary asyncUsageCount codesCount{count} codes(first:20){nodes{id code}} combinesWith{orderDiscounts productDiscounts shippingDiscounts} appliesOncePerCustomer usageLimit} ... on DiscountCodeFreeShipping{title status startsAt endsAt summary asyncUsageCount codesCount{count} codes(first:20){nodes{id code}} combinesWith{orderDiscounts productDiscounts shippingDiscounts} appliesOncePerCustomer usageLimit} ... on DiscountCodeApp{title status startsAt endsAt asyncUsageCount codesCount{count} codes(first:20){nodes{id code}} combinesWith{orderDiscounts productDiscounts shippingDiscounts} appliesOncePerCustomer usageLimit}}"""


def _product_input(args: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    mapping = {
        "title": "title", "descriptionHtml": "descriptionHtml", "handle": "handle",
        "vendor": "vendor", "productType": "productType", "status": "status",
        "categoryId": "category", "tags": "tags", "seo": "seo",
        "templateSuffix": "templateSuffix", "requiresSellingPlan": "requiresSellingPlan",
        "productOptions": "productOptions", "redirectNewHandle": "redirectNewHandle",
        "collectionsToJoin": "collectionsToJoin", "collectionsToLeave": "collectionsToLeave",
    }
    result = {target: args[source] for source, target in mapping.items() if source in args and args[source] is not None}
    if include_id:
        result["id"] = args["id"]
    return result


_RULE_RELATIONS = {
    "TAG": {"EQUALS", "NOT_EQUALS"},
    "TITLE": {"EQUALS", "NOT_EQUALS", "STARTS_WITH", "ENDS_WITH", "CONTAINS", "NOT_CONTAINS"},
    "TYPE": {"EQUALS", "NOT_EQUALS", "STARTS_WITH", "ENDS_WITH", "CONTAINS", "NOT_CONTAINS"},
    "VENDOR": {"EQUALS", "NOT_EQUALS", "STARTS_WITH", "ENDS_WITH", "CONTAINS", "NOT_CONTAINS"},
    "VARIANT_TITLE": {"EQUALS", "NOT_EQUALS", "STARTS_WITH", "ENDS_WITH", "CONTAINS", "NOT_CONTAINS"},
    "VARIANT_PRICE": {"EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN"},
    "VARIANT_COMPARE_AT_PRICE": {"EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN"},
    "VARIANT_INVENTORY": {"EQUALS", "GREATER_THAN", "LESS_THAN"},
    "VARIANT_WEIGHT": {"EQUALS", "NOT_EQUALS", "GREATER_THAN", "LESS_THAN"},
    "IS_PRICE_REDUCED": {"IS_SET", "IS_NOT_SET"},
    "PRODUCT_TAXONOMY_NODE_ID": {"EQUALS", "NOT_EQUALS"},
    "PRODUCT_CATEGORY_ID": {"EQUALS", "NOT_EQUALS"},
    "PRODUCT_CATEGORY_ID_WITH_DESCENDANTS": {"EQUALS", "NOT_EQUALS"},
}
_RULE_NEGATIVE = {"NOT_EQUALS", "NOT_CONTAINS", "IS_NOT_SET"}


def _rule_set_warnings(rule_set: dict[str, Any] | None) -> list[str]:
    """Valida a regra localmente e alerta sobre a armadilha do OU com regra negativa."""
    if not rule_set:
        return []
    rules = rule_set["rules"]
    for rule in rules:
        allowed = _RULE_RELATIONS[rule["column"]]
        if rule["relation"] not in allowed:
            raise ValueError(f"Relação {rule['relation']} não é aceita para {rule['column']}; use uma de {sorted(allowed)}")
    seen: set[tuple[str, str, str]] = set()
    for rule in rules:
        key = (rule["column"], rule["relation"], rule["condition"])
        if key in seen:
            raise ValueError(f"Regra repetida: {key[0]} {key[1]} {key[2]!r}")
        seen.add(key)
    warnings = ["A troca de regra recalcula a membership de forma assíncrona (a mutation devolve um job); confira a contagem depois, não no ato."]
    negatives = [r for r in rules if r["relation"] in _RULE_NEGATIVE]
    if rule_set["appliedDisjunctively"] and negatives:
        warnings.insert(0, "ATENÇÃO: com appliedDisjunctively=true (qualquer condição), uma regra negativa INCLUI todo produto que não bate nela, em vez de excluir. Para excluir, use appliedDisjunctively=false.")
    return warnings


def _grouped_condition_warning(current: dict[str, Any] | None) -> str | None:
    """A API achata condições de múltiplos valores do admin ("Fronha OU Travesseiro") em regras soltas, iguais a regras E."""
    if not current or current.get("appliedDisjunctively"):
        return None
    positive = {"EQUALS", "CONTAINS", "STARTS_WITH", "ENDS_WITH"}
    seen: dict[tuple[str, str], int] = {}
    for rule in current.get("rules") or []:
        if rule["relation"] in positive:
            key = (rule["column"], rule["relation"])
            seen[key] = seen.get(key, 0) + 1
    repeated = [f"{column} {relation}" for (column, relation), count in seen.items() if count > 1]
    if not repeated:
        return None
    return ("ATENÇÃO: a regra atual repete " + ", ".join(repeated) + ". Isso pode ser uma condição de múltiplos valores criada no admin "
            "(os valores valem como OU), que a API devolve achatada e idêntica a regras E. Regravar pela API transforma em E — a coleção "
            "fronhas, por exemplo, cairia de 103 para 0. Confira a contagem na loja antes de aplicar.")


def _collection_input(args: dict[str, Any], *, include_id: bool) -> dict[str, Any]:
    fields = ("title", "descriptionHtml", "handle", "seo", "sortOrder", "templateSuffix", "ruleSet")
    result = {field: args[field] for field in fields if field in args}
    if include_id:
        result["id"] = args["id"]
    return result


def _order_input(args: dict[str, Any]) -> dict[str, Any]:
    fields = ("note", "poNumber", "tags", "customAttributes")
    return {"id": args["id"], **{field: args[field] for field in fields if field in args}}


class ShopifyOperations:
    def __init__(self, client: ShopifyClient, confirmations: ConfirmationManager | None = None):
        self.client = client
        self.confirmations = confirmations or ConfirmationManager()

    def _financial(self, operation, amount, currency):
        return check_financial(self.client.settings.financial_limits_brl, operation, amount, currency)

    async def _recheck_financial(self, context, operation, resource_id):
        if not context or context.get('operation') != operation:
            raise ValueError('Proposta financeira ausente: prepare novamente a operação')
        if operation == 'cancel_order':
            result = await self.client.graphql('query FinancialOrderCheck($id:ID!){order(id:$id){currentTotalPriceSet{shopMoney{amount currencyCode}}}}', {'id': resource_id})
            value = ((result.get('data') or {}).get('order') or {}).get('currentTotalPriceSet', {}).get('shopMoney', {})
        else:
            result = await self.client.graphql('query FinancialDraftCheck($id:ID!){draftOrder(id:$id){totalPriceSet{shopMoney{amount currencyCode}}}}', {'id': resource_id})
            value = ((result.get('data') or {}).get('draftOrder') or {}).get('totalPriceSet', {}).get('shopMoney', {})
        current = self._financial(operation, value.get('amount'), value.get('currencyCode'))
        if current['amount'] != context['amount'] or current['currency'] != context['currency']:
            raise ValueError('Total mudou após a proposta: prepare e aprove novamente')

    async def get_shop(self, _: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query ShopContext { shop { id name email contactEmail myshopifyDomain primaryDomain { id host url } currencyCode enabledPresentmentCurrencies ianaTimezone timezoneAbbreviation weightUnit taxesIncluded taxShipping plan { displayName partnerDevelopment shopifyPlus } resourceLimits { maxProductVariants } } }""")
        return {"shop": result["data"]["shop"], "api": result["meta"]}

    async def get_access_scopes(self, _: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query AccessScopes { currentAppInstallation { id accessScopes { handle description } } }""")
        installation = result["data"]["currentAppInstallation"]
        scopes = sorted(installation.get("accessScopes") or [], key=lambda item: item["handle"])
        return {"appInstallationId": installation["id"], "scopes": scopes, "count": len(scopes)}

    async def shopifyql_query(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ShopifyQL($q:String!){shopifyqlQuery(query:$q){__typename parseErrors tableData{columns{name dataType displayName} rows}}}"""
        result = await self.client.graphql(query, {"q": args["query"]})
        return {"shopifyql": result["data"]["shopifyqlQuery"]}

    async def list_publications(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Publications($first:Int!,$after:String){publications(first:$first,after:$after){edges{cursor node{id name autoPublish supportsFuturePublishing catalog{__typename id title} includedProductsCount{count}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after")})
        return _connection(result["data"], "publications")

    async def get_publication(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Publication($id:ID!){publication(id:$id){id name autoPublish supportsFuturePublishing catalog{__typename id title} includedProductsCount{count}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"publication": result["data"]["publication"]}

    async def list_product_types(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ProductTypes($first:Int!,$after:String){productTypes(first:$first,after:$after){edges{cursor node}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after")})
        return _connection(result["data"], "productTypes")

    async def list_product_vendors(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ProductVendors($first:Int!,$after:String){productVendors(first:$first,after:$after){edges{cursor node}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after")})
        return _connection(result["data"], "productVendors")

    async def list_products(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Products($first:Int!,$after:String,$query:String){products(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){edges{cursor node{id title handle status vendor productType tags updatedAt totalInventory seo{title description} featuredMedia{preview{image{url altText}}} variants(first:20){nodes{id title sku barcode price compareAtPrice inventoryQuantity requiresComponents}}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "products")

    async def get_product(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Product($id:ID!){product(id:$id){id title handle descriptionHtml status vendor productType tags createdAt updatedAt totalInventory seo{title description} category{id fullName} media(first:20){nodes{mediaContentType alt preview{image{url}}}} variants(first:100){nodes{id title sku barcode price compareAtPrice inventoryQuantity inventoryItem{id tracked} selectedOptions{name value} requiresComponents productVariantComponents(first:25){nodes{id quantity productVariant{id title sku price product{id title handle}}}}}} collections(first:50){nodes{id title handle}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"product": result["data"]["product"]}

    async def get_product_by_handle(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ProductByHandle($identifier:ProductIdentifierInput!){productByIdentifier(identifier:$identifier){id title handle descriptionHtml status vendor productType tags createdAt updatedAt totalInventory seo{title description} category{id fullName} options{id name position optionValues{id name hasVariants}} variants(first:100){nodes{id title displayName sku barcode price compareAtPrice inventoryQuantity inventoryPolicy taxable availableForSale inventoryItem{id tracked requiresShipping measurement{weight{value unit}}} selectedOptions{name value} requiresComponents productVariantComponents(first:25){nodes{id quantity productVariant{id title sku price product{id title handle}}}}}}}}"""
        result = await self.client.graphql(query, {"identifier": {"handle": args["handle"]}})
        return {"product": result["data"]["productByIdentifier"]}

    async def count_products(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ProductCount($query:String){productsCount(query:$query){count precision}}"""
        result = await self.client.graphql(query, {"query": args.get("query")})
        return {"productsCount": result["data"]["productsCount"]}

    async def get_product_360(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Product360($id:ID!,$first:Int!,$after:String){product(id:$id){id title handle descriptionHtml status vendor productType tags templateSuffix createdAt updatedAt totalInventory tracksInventory requiresSellingPlan seo{title description} category{id fullName} options{id name position optionValues{id name hasVariants}} media(first:50){nodes{id mediaContentType alt status preview{status image{url altText}}}} collections(first:50){nodes{id title handle}} metafields(first:100){nodes{id namespace key type value compareDigest updatedAt}} resourcePublicationsV2(first:50){nodes{isPublished publishDate publication{id name autoPublish}}} variants(first:$first,after:$after){edges{cursor node{id title displayName sku barcode price compareAtPrice inventoryQuantity inventoryPolicy taxable availableForSale requiresComponents productVariantComponents(first:25){nodes{id quantity productVariant{id title sku price product{id title handle}}}} selectedOptions{name value} inventoryItem{id tracked requiresShipping measurement{weight{value unit}} inventoryLevels(first:20){nodes{id location{id name isActive} quantities(names:[\"available\",\"on_hand\",\"committed\",\"reserved\",\"incoming\"]){name quantity}}}}}}pageInfo{hasNextPage endCursor}}}}"""
        result = await self.client.graphql(query, {"id": args["id"], "first": min(int(args.get("variantFirst", 25)), 50), "after": args.get("variantAfter")})
        product = result["data"]["product"]
        return {"product": product, "limits": {"variants": 50, "inventoryLevelsPerVariant": 20, "metafields": 100, "media": 50, "collections": 50, "publications": 50}, "complete": bool(product is None or not product["variants"]["pageInfo"]["hasNextPage"])}

    async def audit_product_data(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ProductDataAudit($first:Int!,$after:String,$query:String){products(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){edges{cursor node{id title handle status vendor productType descriptionHtml category{id} seo{title description} featuredMedia{id} variants(first:100){nodes{id title sku barcode price inventoryQuantity inventoryItem{tracked}}}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        connection = result["data"]["products"]
        audited = []
        totals: dict[str, int] = {}
        for edge in connection["edges"]:
            product = edge["node"]
            issues = []
            checks = ((not product.get("vendor"), "MISSING_VENDOR"), (not product.get("productType"), "MISSING_PRODUCT_TYPE"), (not product.get("category"), "MISSING_CATEGORY"), (not product.get("descriptionHtml"), "MISSING_DESCRIPTION"), (not (product.get("seo") or {}).get("title"), "MISSING_SEO_TITLE"), (not (product.get("seo") or {}).get("description"), "MISSING_SEO_DESCRIPTION"), (not product.get("featuredMedia"), "MISSING_MEDIA"))
            issues.extend(code for failed, code in checks if failed)
            variants = product.get("variants", {}).get("nodes", [])
            if any(not variant.get("sku") for variant in variants): issues.append("VARIANT_MISSING_SKU")
            if any(not variant.get("barcode") for variant in variants): issues.append("VARIANT_MISSING_BARCODE")
            for code in issues: totals[code] = totals.get(code, 0) + 1
            audited.append({"id": product["id"], "title": product["title"], "handle": product["handle"], "status": product["status"], "issues": issues, "issueCount": len(issues), "variantCountInPage": len(variants)})
        return {"items": audited, "summary": {"productsAudited": len(audited), "productsWithIssues": sum(bool(item["issues"]) for item in audited), "issueCounts": totals}, "pageInfo": connection["pageInfo"], "limits": {"variantsPerProduct": 100}}

    async def list_product_variants(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ProductVariants($first:Int!,$after:String,$query:String){productVariants(first:$first,after:$after,query:$query,sortKey:RELEVANCE){edges{cursor node{id title displayName sku barcode price compareAtPrice inventoryQuantity inventoryPolicy taxable availableForSale createdAt updatedAt product{id title handle status} inventoryItem{id tracked requiresShipping measurement{weight{value unit}}} selectedOptions{name value} requiresComponents}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "productVariants")

    async def get_product_variant(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ProductVariant($id:ID!){productVariant(id:$id){id title displayName sku barcode price compareAtPrice inventoryQuantity inventoryPolicy taxable availableForSale createdAt updatedAt product{id title handle status} inventoryItem{id tracked requiresShipping measurement{weight{value unit}}} selectedOptions{name value} requiresComponents productVariantComponents(first:25){nodes{id quantity productVariant{id title sku price product{id title handle}}}} media(first:20){nodes{id mediaContentType alt preview{image{url}}}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"variant": result["data"]["productVariant"]}

    async def get_product_variant_by_sku(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query VariantBySku($query:String!){productVariants(first:2,query:$query){nodes{id title displayName sku barcode price compareAtPrice inventoryQuantity inventoryPolicy taxable availableForSale product{id title handle status} inventoryItem{id tracked requiresShipping measurement{weight{value unit}}} selectedOptions{name value} requiresComponents productVariantComponents(first:25){nodes{id quantity productVariant{id title sku price product{id title handle}}}}}}}"""
        result = await self.client.graphql(query, {"query": _search_exact("sku", args["sku"])})
        variants = result["data"]["productVariants"]["nodes"]
        if len(variants) > 1:
            raise ShopifyError("SKU ambíguo: mais de uma variante usa este valor", details={"matchCountAtLeast": 2})
        return {"variant": variants[0] if variants else None}

    async def list_orders(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Orders($first:Int!,$after:String,$query:String){orders(first:$first,after:$after,query:$query,sortKey:PROCESSED_AT,reverse:true){edges{cursor node{id name createdAt processedAt displayFinancialStatus displayFulfillmentStatus currencyCode currentTotalPriceSet{shopMoney{amount currencyCode}} customer{id displayName email} tags}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "orders")

    async def get_order(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Order($id:ID!){order(id:$id){id name createdAt updatedAt processedAt closedAt cancelledAt cancelReason confirmed test note poNumber email phone displayFinancialStatus displayFulfillmentStatus currencyCode subtotalPriceSet{shopMoney{amount currencyCode}} totalDiscountsSet{shopMoney{amount currencyCode}} totalShippingPriceSet{shopMoney{amount currencyCode}} totalTaxSet{shopMoney{amount currencyCode}} currentTotalPriceSet{shopMoney{amount currencyCode}} totalRefundedSet{shopMoney{amount currencyCode}} customer{id displayName email phone metafields(first:50){nodes{namespace key value}}} billingAddress{name address1 address2 city provinceCode zip countryCodeV2 phone company} shippingAddress{name address1 address2 city provinceCode zip countryCodeV2 phone company} localizationExtensions(first:20){nodes{countryCode purpose title value}} metafields(first:50){nodes{namespace key value}} discountCodes discountApplications(first:30){nodes{__typename targetType allocationMethod value{__typename ... on MoneyV2{amount currencyCode} ... on PricingPercentageValue{percentage}} ... on DiscountCodeApplication{code} ... on AutomaticDiscountApplication{title} ... on ManualDiscountApplication{title} ... on ScriptDiscountApplication{title}}} customAttributes{key value} shippingLines(first:20){nodes{id title code source discountedPriceSet{shopMoney{amount currencyCode}}}} lineItems(first:100){nodes{id name sku quantity currentQuantity refundableQuantity unfulfilledQuantity originalUnitPriceSet{shopMoney{amount currencyCode}} discountedTotalSet{shopMoney{amount currencyCode}} product{id title handle} variant{id title sku}}} fulfillments{id status createdAt updatedAt deliveredAt trackingInfo{company number url}} tags}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"order": result["data"]["order"]}

    async def count_orders(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query OrdersCount($query:String,$limit:Int){ordersCount(query:$query,limit:$limit){count precision}}"""
        result = await self.client.graphql(query, {"query": args.get("query"), "limit": args.get("limit", 10000)})
        return {"ordersCount": result["data"]["ordersCount"]}

    async def get_order_financials(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query OrderFinancials($id:ID!){order(id:$id){id name displayFinancialStatus netPaymentSet{shopMoney{amount currencyCode}} totalCapturableSet{shopMoney{amount currencyCode}} totalReceivedSet{shopMoney{amount currencyCode}} totalRefundedSet{shopMoney{amount currencyCode}} transactions(first:100){id createdAt processedAt kind status gateway formattedGateway amountSet{shopMoney{amount currencyCode}} parentTransaction{id} errorCode receiptJson} refunds{id createdAt note totalRefundedSet{shopMoney{amount currencyCode}} transactions(first:100){nodes{id kind status gateway amountSet{shopMoney{amount currencyCode}}}} refundLineItems(first:100){nodes{quantity restockType subtotalSet{shopMoney{amount currencyCode}} lineItem{id name sku}}}} returns(first:100){nodes{id name status createdAt closedAt totalQuantity}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"order": result["data"]["order"]}

    async def get_order_360(self, args: dict[str, Any]) -> dict[str, Any]:
        order = (await self.get_order(args))["order"]
        if order is None:
            return {"order": None, "financials": None, "fulfillmentOrders": [], "complete": True}
        financials = (await self.get_order_financials(args))["order"]
        fulfillment = await self.list_order_fulfillment_orders({"id": args["id"], "first": 100})
        return {"order": order, "financials": financials, "fulfillmentOrders": fulfillment["items"], "fulfillmentPageInfo": fulfillment["pageInfo"], "complete": not fulfillment["pageInfo"].get("hasNextPage", False), "containsPii": True}

    async def list_order_fulfillment_orders(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query OrderFulfillmentOrders($id:ID!,$first:Int!,$after:String){order(id:$id){id name fulfillmentOrders(first:$first,after:$after){edges{cursor node{id status requestStatus createdAt updatedAt fulfillAt fulfillBy assignedLocation{name location{id name isActive}} destination{firstName lastName company address1 address2 city province zip countryCode phone} supportedActions{action externalUrl} lineItems(first:100){nodes{id totalQuantity remainingQuantity inventoryItemId requiresShipping lineItem{id name sku quantity currentQuantity}}}}}pageInfo{hasNextPage endCursor}}}}"""
        result = await self.client.graphql(query, {"id": args["id"], "first": _page_size(args.get("first")), "after": args.get("after")})
        order = result["data"]["order"]
        if order is None:
            return {"order": None, "items": [], "pageInfo": {}}
        connection = _connection(order, "fulfillmentOrders")
        return {"order": {"id": order["id"], "name": order["name"]}, **connection}

    async def prepare_order_update(self, args: dict[str, Any]) -> dict[str, Any]:
        order_input = _order_input(args)
        if set(order_input) == {"id"}:
            raise ValueError("Informe ao menos um campo para alterar")
        result = await self.client.graphql("""query OrderUpdatePreview($id:ID!){order(id:$id){id name cancelledAt closedAt note poNumber tags customAttributes{key value}}}""", {"id": args["id"]})
        order = result["data"]["order"]
        if order is None:
            raise ShopifyError("Pedido não encontrado")
        before = {field: order.get(field) for field in ("note", "poNumber", "tags", "customAttributes")}
        after = {**before, **{key: value for key, value in order_input.items() if key != "id"}}
        token = self.confirmations.issue("shopify_update_order", order_input)
        warnings = []
        if "tags" in args:
            warnings.append("tags substitui integralmente a lista atual.")
        if "customAttributes" in args:
            warnings.append("customAttributes substitui integralmente a lista atual.")
        if order.get("cancelledAt"):
            warnings.append("O pedido está cancelado; a alteração afeta apenas seus dados administrativos.")
        return {"order": {"id": order["id"], "name": order["name"], "cancelledAt": order.get("cancelledAt"), "closedAt": order.get("closedAt")}, "before": before, "after": after, "willChange": before_changed(before, after), "warnings": warnings, **token}

    async def update_order(self, args: dict[str, Any]) -> dict[str, Any]:
        order_input = _order_input(args)
        self._require_write(args, "shopify_update_order", order_input)
        query = """mutation OrderUpdate($input:OrderInput!){orderUpdate(input:$input){order{id name updatedAt note poNumber tags customAttributes{key value}} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"input": order_input})
        return {"success": True, "operation": "orderUpdate", **mutation_result(result, "orderUpdate")}

    @staticmethod
    def _fulfillment_create_variables(args: dict[str, Any]) -> dict[str, Any]:
        fulfillment = {
            "lineItemsByFulfillmentOrder": [
                {"fulfillmentOrderId": group["fulfillmentOrderId"], "fulfillmentOrderLineItems": group["lineItems"]}
                for group in args["groups"]
            ],
            "notifyCustomer": args["notifyCustomer"],
        }
        if "tracking" in args:
            fulfillment["trackingInfo"] = args["tracking"]
        result = {"fulfillment": fulfillment}
        if "message" in args:
            result["message"] = args["message"]
        return result

    async def prepare_fulfillment_create(self, args: dict[str, Any]) -> dict[str, Any]:
        tracking = args.get("tracking")
        if tracking and "urls" in tracking and len(tracking["urls"]) != len(tracking["numbers"]):
            raise ValueError("urls deve ter a mesma quantidade e ordem de numbers")
        order_ids = [group["fulfillmentOrderId"] for group in args["groups"]]
        if len(set(order_ids)) != len(order_ids):
            raise ValueError("Cada fulfillment order pode aparecer apenas uma vez")
        result = await self.client.graphql("""query FulfillmentCreatePreview($ids:[ID!]!){nodes(ids:$ids){... on FulfillmentOrder{id status requestStatus order{id name} assignedLocation{name location{id name}} supportedActions{action} lineItems(first:512){nodes{id totalQuantity remainingQuantity lineItem{id name sku}}}}}}""", {"ids": order_ids})
        found = {node["id"]: node for node in result["data"]["nodes"] if node}
        missing = sorted(set(order_ids) - set(found))
        if missing:
            raise ShopifyError("Uma ou mais fulfillment orders não foram encontradas", details={"missingIds": missing})
        if len({node["order"]["id"] for node in found.values()}) != 1 or len({node["assignedLocation"]["location"]["id"] for node in found.values()}) != 1:
            raise ShopifyError("Fulfillment orders devem pertencer ao mesmo pedido e local")
        selected = []
        for group in args["groups"]:
            fulfillment_order = found[group["fulfillmentOrderId"]]
            if "CREATE_FULFILLMENT" not in {action["action"] for action in fulfillment_order["supportedActions"]}:
                raise ShopifyError("Fulfillment order não permite criar atendimento", details={"fulfillmentOrderId": fulfillment_order["id"], "status": fulfillment_order["status"]})
            available = {item["id"]: item for item in fulfillment_order["lineItems"]["nodes"]}
            ids = [item["id"] for item in group["lineItems"]]
            if len(set(ids)) != len(ids):
                raise ValueError("Cada item pode aparecer apenas uma vez no fulfillment order")
            invalid = sorted(set(ids) - set(available))
            if invalid:
                raise ShopifyError("Itens não pertencem ao fulfillment order", details={"invalidIds": invalid})
            for requested in group["lineItems"]:
                current = available[requested["id"]]
                if requested["quantity"] > current["remainingQuantity"]:
                    raise ShopifyError("Quantidade solicitada excede a quantidade restante", details={"lineItemId": requested["id"], "requested": requested["quantity"], "remaining": current["remainingQuantity"]})
                selected.append({"fulfillmentOrderId": fulfillment_order["id"], "lineItem": current, "quantity": requested["quantity"]})
        mutation_args = self._fulfillment_create_variables(args)
        token = self.confirmations.issue("shopify_create_fulfillment", mutation_args)
        first = next(iter(found.values()))
        warnings = ["O cliente receberá notificação de envio."] if args["notifyCustomer"] else []
        return {"order": first["order"], "location": first["assignedLocation"], "selectedItems": selected, "tracking": tracking, "notifyCustomer": args["notifyCustomer"], "warnings": warnings, **token}

    async def create_fulfillment(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = self._fulfillment_create_variables(args)
        self._require_write(args, "shopify_create_fulfillment", mutation_args)
        query = """mutation FulfillmentCreate($fulfillment:FulfillmentInput!,$message:String){fulfillmentCreate(fulfillment:$fulfillment,message:$message){fulfillment{id status createdAt updatedAt order{id name} trackingInfo{company number url} fulfillmentLineItems(first:100){nodes{quantity lineItem{id name sku}}}} userErrors{field message}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "fulfillmentCreate", **mutation_result(result, "fulfillmentCreate")}

    async def prepare_fulfillment_tracking_update(self, args: dict[str, Any]) -> dict[str, Any]:
        if "urls" in args["tracking"] and len(args["tracking"]["urls"]) != len(args["tracking"]["numbers"]):
            raise ValueError("urls deve ter a mesma quantidade e ordem de numbers")
        result = await self.client.graphql("""query FulfillmentTrackingPreview($id:ID!){fulfillment(id:$id){id status order{id name} trackingInfo{company number url}}}""", {"id": args["fulfillmentId"]})
        fulfillment = result["data"]["fulfillment"]
        if fulfillment is None:
            raise ShopifyError("Fulfillment não encontrado")
        mutation_args = {"fulfillmentId": args["fulfillmentId"], "trackingInfoInput": args["tracking"], "notifyCustomer": args["notifyCustomer"]}
        token = self.confirmations.issue("shopify_update_fulfillment_tracking", mutation_args)
        warnings = ["O cliente será notificado e poderá receber futuras atualizações de rastreio."] if args["notifyCustomer"] else []
        return {"fulfillment": {"id": fulfillment["id"], "status": fulfillment["status"], "order": fulfillment["order"]}, "before": fulfillment["trackingInfo"], "after": args["tracking"], "notifyCustomer": args["notifyCustomer"], "warnings": warnings, **token}

    async def update_fulfillment_tracking(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"fulfillmentId": args["fulfillmentId"], "trackingInfoInput": args["tracking"], "notifyCustomer": args["notifyCustomer"]}
        self._require_write(args, "shopify_update_fulfillment_tracking", mutation_args)
        query = """mutation FulfillmentTrackingUpdate($fulfillmentId:ID!,$trackingInfoInput:FulfillmentTrackingInput!,$notifyCustomer:Boolean!){fulfillmentTrackingInfoUpdate(fulfillmentId:$fulfillmentId,trackingInfoInput:$trackingInfoInput,notifyCustomer:$notifyCustomer){fulfillment{id status updatedAt order{id name} trackingInfo{company number url}} userErrors{field message}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "fulfillmentTrackingInfoUpdate", **mutation_result(result, "fulfillmentTrackingInfoUpdate")}

    @staticmethod
    def _order_cancel_variables(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "orderId": args["orderId"], "reason": args["reason"],
            "refundMethod": {"originalPaymentMethodsRefund": args["refundOriginalPaymentMethods"]},
            "restock": args["restock"], "notifyCustomer": args["notifyCustomer"], "staffNote": args["staffNote"],
        }

    async def prepare_order_cancel(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query OrderCancelPreview($id:ID!){order(id:$id){id name cancelledAt cancelReason test confirmed displayFinancialStatus displayFulfillmentStatus currentTotalPriceSet{shopMoney{amount currencyCode}} netPaymentSet{shopMoney{amount currencyCode}} totalRefundedSet{shopMoney{amount currencyCode}} transactions(first:100){id kind status gateway amountSet{shopMoney{amount currencyCode}}} fulfillmentOrders(first:100){nodes{id status requestStatus assignedLocation{name location{id name isActive}}}} returns(first:100){nodes{id name status totalQuantity}}}}""", {"id": args["orderId"]})
        order = result["data"]["order"]
        if order is None:
            raise ShopifyError("Pedido não encontrado")
        if order.get("cancelledAt"):
            raise ShopifyError("Pedido já está cancelado", details={"cancelledAt": order["cancelledAt"], "cancelReason": order.get("cancelReason")})
        active_returns = [item for item in order["returns"]["nodes"] if item["status"] not in {"CANCELED", "CLOSED", "DECLINED"}]
        if active_returns:
            raise ShopifyError("Pedido possui devolução ativa e não pode ser preparado para cancelamento", details={"returns": active_returns})
        mutation_args = self._order_cancel_variables(args)
        amount = order.get('currentTotalPriceSet', {}).get('shopMoney', {})
        financial = self._financial('cancel_order', amount.get('amount'), amount.get('currencyCode'))
        token = self.confirmations.issue("shopify_cancel_order", mutation_args, context=financial)
        token['financialSummary'] = financial
        warnings = ["O cancelamento é irreversível."]
        if args["refundOriginalPaymentMethods"]:
            warnings.append("Os valores elegíveis serão reembolsados aos meios de pagamento originais.")
        else:
            warnings.append("Pagamentos capturados não serão reembolsados automaticamente; autorizações ainda podem ser anuladas pela Shopify.")
        if args["restock"]:
            warnings.append("O estoque comprometido será devolvido quando os locais permitirem.")
        if args["notifyCustomer"]:
            warnings.append("O cliente receberá uma notificação de cancelamento.")
        return {"order": order, "requested": mutation_args, "financial": True, "irreversible": True, "warnings": warnings, **token}

    async def cancel_order(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = self._order_cancel_variables(args)
        context = self._require_write(args, "shopify_cancel_order", mutation_args)
        await self._recheck_financial(context, 'cancel_order', args['orderId'])
        query = """mutation OrderCancel($orderId:ID!,$reason:OrderCancelReason!,$refundMethod:OrderCancelRefundMethodInput!,$restock:Boolean!,$notifyCustomer:Boolean!,$staffNote:String!){orderCancel(orderId:$orderId,reason:$reason,refundMethod:$refundMethod,restock:$restock,notifyCustomer:$notifyCustomer,staffNote:$staffNote){job{id done} orderCancelUserErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        payload = result["data"].get("orderCancel") or {}
        if payload.get("orderCancelUserErrors"):
            raise ShopifyError("Shopify rejeitou a operação orderCancel", details=payload["orderCancelUserErrors"])
        return {"success": True, "operation": "orderCancel", **payload}

    @staticmethod
    def _refund_input(args: dict[str, Any]) -> dict[str, Any]:
        return {
            "orderId": args["orderId"], "refundLineItems": args["lineItems"],
            "notify": args["notifyCustomer"], "note": args["note"],
            "transactions": args["transactions"], "currency": args["currency"],
            "allowOverRefunding": False,
        }

    async def prepare_refund_create(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = [item["lineItemId"] for item in args["lineItems"]]
        if len(set(ids)) != len(ids):
            raise ValueError("Cada line item pode aparecer apenas uma vez")
        for item in args["lineItems"]:
            if item["restockType"] == "NO_RESTOCK" and "locationId" in item:
                raise ValueError("NO_RESTOCK não aceita locationId")
            if item["restockType"] in {"CANCEL", "RETURN"} and "locationId" not in item:
                raise ValueError("CANCEL e RETURN exigem locationId")
        result = await self.client.graphql("""query RefundPreview($id:ID!,$refundLineItems:[RefundLineItemInput!]!){order(id:$id){id name cancelledAt displayFinancialStatus currencyCode presentmentCurrencyCode lineItems(first:250){nodes{id name sku quantity refundableQuantity restockable unfulfilledQuantity}} suggestedRefund(refundLineItems:$refundLineItems,refundMethodAllocation:ORIGINAL_PAYMENT_METHODS){amountSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} maximumRefundableSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} subtotalSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalTaxSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} refundLineItems{quantity restockType location{id name} subtotalSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalTaxSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} lineItem{id name sku}} suggestedTransactions{kind gateway formattedGateway amountSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} maximumRefundableSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} parentTransaction{id}}}}}""", {"id": args["orderId"], "refundLineItems": args["lineItems"]})
        order = result["data"]["order"]
        if order is None:
            raise ShopifyError("Pedido não encontrado")
        available = {item["id"]: item for item in order["lineItems"]["nodes"]}
        invalid = sorted(set(ids) - set(available))
        if invalid:
            raise ShopifyError("Itens não pertencem ao pedido", details={"invalidIds": invalid})
        for requested in args["lineItems"]:
            current = available[requested["lineItemId"]]
            if requested["quantity"] > current["refundableQuantity"]:
                raise ShopifyError("Quantidade excede o saldo reembolsável", details={"lineItemId": current["id"], "requested": requested["quantity"], "refundable": current["refundableQuantity"]})
            if requested["restockType"] != "NO_RESTOCK" and not current["restockable"]:
                raise ShopifyError("Item não pode ser restocado", details={"lineItemId": current["id"]})
        suggestion = order["suggestedRefund"]
        transactions = []
        currencies = set()
        for suggested in suggestion["suggestedTransactions"]:
            money = suggested["amountSet"]["presentmentMoney"]
            currencies.add(money["currencyCode"])
            if suggested.get("gateway") and money["amount"] != "0.00":
                transaction = {"orderId": args["orderId"], "kind": "REFUND", "gateway": suggested["gateway"], "amount": money["amount"]}
                if suggested.get("parentTransaction"):
                    transaction["parentId"] = suggested["parentTransaction"]["id"]
                transactions.append(transaction)
        if len(currencies) > 1:
            raise ValueError('Reembolso com moedas diferentes: use o sistema de origem')
        currency = next(iter(currencies), order["presentmentCurrencyCode"])
        idempotency_key = str(uuid4())
        apply_args = {**args, "transactions": transactions, "currency": currency}
        mutation_args = {"input": self._refund_input(apply_args), "idempotencyKey": idempotency_key}
        total = sum((parse_money(t['amount']) for t in transactions), parse_money('0'))
        financial = self._financial('refund', total, currency)
        token = self.confirmations.issue("shopify_create_refund", mutation_args, context=financial)
        token['financialSummary'] = financial
        warnings = ["Esta operação movimenta valores e não pode ser desfeita automaticamente."]
        if args["notifyCustomer"]:
            warnings.append("O cliente receberá notificação do refund.")
        return {"order": {key: value for key, value in order.items() if key not in {"lineItems", "suggestedRefund"}}, "selectedLineItems": [available[item_id] for item_id in ids], "suggestedRefund": suggestion, "transactions": transactions, "currency": currency, "idempotencyKey": idempotency_key, "financial": True, "warnings": warnings, **token}

    async def create_refund(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"input": self._refund_input(args), "idempotencyKey": args["idempotencyKey"]}
        context = self._require_write(args, "shopify_create_refund", mutation_args)
        financial = self._financial('refund', sum((parse_money(t['amount']) for t in args['transactions']), parse_money('0')), args['currency'])
        if not context or context != financial:
            raise ValueError('Proposta financeira inválida: prepare novamente')
        query = """mutation RefundCreate($input:RefundInput!,$idempotencyKey:String!){refundCreate(input:$input) @idempotent(key:$idempotencyKey){order{id name displayFinancialStatus totalRefundedSet{shopMoney{amount currencyCode}}} refund{id createdAt note totalRefundedSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} refundLineItems(first:100){nodes{quantity restockType location{id name} lineItem{id name sku}}} transactions(first:100){nodes{id kind status gateway amountSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}}}}} userErrors{field message}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "refundCreate", "idempotencyKey": args["idempotencyKey"], **mutation_result(result, "refundCreate")}

    async def list_return_reason_definitions(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ReturnReasonDefinitions($first:Int!,$after:String,$query:String){returnReasonDefinitions(first:$first,after:$after,query:$query){edges{cursor node{id name}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "returnReasonDefinitions")

    async def list_returnable_fulfillments(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query ReturnableFulfillments($orderId:ID!,$first:Int!,$after:String){returnableFulfillments(orderId:$orderId,first:$first,after:$after){edges{cursor node{id fulfillment{id status createdAt deliveredAt location{id name}} returnableFulfillmentLineItems(first:100){nodes{quantity fulfillmentLineItem{id quantity lineItem{id name sku quantity originalUnitPriceSet{shopMoney{amount currencyCode}}}}}}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"orderId": args["orderId"], "first": _page_size(args.get("first")), "after": args.get("after")})
        return _connection(result["data"], "returnableFulfillments")

    async def get_return(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Return($id:ID!){return(id:$id){id name status createdAt closedAt requestApprovedAt totalQuantity order{id name} returnLineItems(first:100){nodes{... on ReturnLineItem{id quantity returnReasonDefinition{id name} returnReasonNote fulfillmentLineItem{id lineItem{id name sku}}}}} reverseFulfillmentOrders(first:100){nodes{id status lineItems(first:100){nodes{id totalQuantity}}}} refunds(first:100){nodes{id createdAt totalRefundedSet{shopMoney{amount currencyCode}}}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"return": result["data"]["return"]}

    @staticmethod
    def _return_input(args: dict[str, Any]) -> dict[str, Any]:
        value = {"orderId": args["orderId"], "returnLineItems": args["returnLineItems"]}
        if args.get("requestedAt") is not None:
            value["requestedAt"] = args["requestedAt"]
        return value

    async def prepare_return_create(self, args: dict[str, Any]) -> dict[str, Any]:
        item_ids = [item["fulfillmentLineItemId"] for item in args["returnLineItems"]]
        if len(set(item_ids)) != len(item_ids):
            raise ValueError("Cada fulfillment line item pode aparecer apenas uma vez")
        reason_ids = sorted({item["returnReasonDefinitionId"] for item in args["returnLineItems"]})
        result = await self.client.graphql("""query ReturnPreview($orderId:ID!,$reasonIds:[ID!]!){order(id:$orderId){id name cancelledAt} returnableFulfillments(orderId:$orderId,first:100){nodes{id fulfillment{id status location{id name}} returnableFulfillmentLineItems(first:100){nodes{quantity fulfillmentLineItem{id quantity lineItem{id name sku}}}}}} nodes(ids:$reasonIds){... on ReturnReasonDefinition{id name}}}""", {"orderId": args["orderId"], "reasonIds": reason_ids})
        order = result["data"]["order"]
        if order is None:
            raise ShopifyError("Pedido não encontrado")
        available: dict[str, dict[str, Any]] = {}
        for fulfillment in result["data"]["returnableFulfillments"]["nodes"]:
            for entry in fulfillment["returnableFulfillmentLineItems"]["nodes"]:
                available[entry["fulfillmentLineItem"]["id"]] = {**entry, "returnableFulfillmentId": fulfillment["id"], "fulfillment": fulfillment.get("fulfillment")}
        invalid = sorted(set(item_ids) - set(available))
        if invalid:
            raise ShopifyError("Itens não estão elegíveis para devolução", details={"invalidIds": invalid})
        for requested in args["returnLineItems"]:
            current = available[requested["fulfillmentLineItemId"]]
            if requested["quantity"] > current["quantity"]:
                raise ShopifyError("Quantidade excede o saldo devolvível", details={"fulfillmentLineItemId": requested["fulfillmentLineItemId"], "requested": requested["quantity"], "returnable": current["quantity"]})
        reasons = {node["id"]: node for node in result["data"]["nodes"] if node is not None}
        invalid_reasons = sorted(set(reason_ids) - set(reasons))
        if invalid_reasons:
            raise ShopifyError("Motivos de devolução inválidos ou indisponíveis", details={"invalidIds": invalid_reasons})
        mutation_args = {"returnInput": self._return_input(args)}
        token = self.confirmations.issue("shopify_create_return", mutation_args)
        return {"order": order, "selectedItems": [available[item_id] for item_id in item_ids], "reasons": [reasons[reason_id] for reason_id in reason_ids], "requested": mutation_args["returnInput"], "warnings": ["A devolução será criada aprovada e OPEN.", "Refund, frete reverso, inspeção e restock são operações separadas."], **token}

    async def create_return(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"returnInput": self._return_input(args)}
        self._require_write(args, "shopify_create_return", mutation_args)
        query = """mutation ReturnCreate($returnInput:ReturnInput!){returnCreate(returnInput:$returnInput){return{id name status createdAt totalQuantity order{id name} returnLineItems(first:100){nodes{... on ReturnLineItem{id quantity returnReasonDefinition{id name} returnReasonNote fulfillmentLineItem{id lineItem{id name sku}}}}}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "returnCreate", **mutation_result(result, "returnCreate")}

    async def list_draft_orders(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query DraftOrders($first:Int!,$after:String,$query:String){draftOrders(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){edges{cursor node{id name status createdAt updatedAt completedAt invoiceSentAt email currencyCode totalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} customer{id displayName email} tags order{id name}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "draftOrders")

    async def get_draft_order(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query DraftOrder($id:ID!){draftOrder(id:$id){id name status createdAt updatedAt completedAt invoiceSentAt invoiceUrl email note2 currencyCode presentmentCurrencyCode taxesIncluded taxExempt subtotalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalDiscountsSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalTaxSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} customer{id displayName email phone} shippingAddress{name address1 address2 city provinceCode zip countryCodeV2 phone} billingAddress{name address1 address2 city provinceCode zip countryCodeV2 phone} lineItems(first:250){nodes{id name sku quantity originalUnitPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} discountedTotalSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} product{id title} variant{id title sku requiresComponents} components{id sku title quantity variant{id title sku}}}} appliedDiscount{title description value valueType amountSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}}} discountCodes shippingLine{title custom originalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}}} tags order{id name}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"draftOrder": result["data"]["draftOrder"], "containsPII": True}

    @staticmethod
    def _draft_order_input(args: dict[str, Any]) -> dict[str, Any]:
        fields = ("lineItems", "customerId", "email", "note", "tags", "taxExempt", "useCustomerDefaultAddress", "acceptAutomaticDiscounts", "discountCodes")
        return {field: args[field] for field in fields if field in args}

    async def prepare_draft_order_create(self, args: dict[str, Any]) -> dict[str, Any]:
        variant_ids = [item["variantId"] for item in args["lineItems"]]
        if len(set(variant_ids)) != len(variant_ids):
            raise ValueError("Cada variante pode aparecer apenas uma vez; consolide a quantidade")
        draft_input = self._draft_order_input(args)
        result = await self.client.graphql("""mutation DraftOrderCalculate($input:DraftOrderInput!,$ids:[ID!]!){draftOrderCalculate(input:$input){calculatedDraftOrder{customer{id displayName email} presentmentCurrencyCode subtotalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalDiscountsSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalTaxSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} totalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} lineItems{title variant{id title sku requiresComponents availableForSale inventoryQuantity product{id title status}} quantity discountedTotalSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} components{sku title quantity variant{id title sku}}} discountCodes{code applicable rejectionReason}} userErrors{field message}} nodes(ids:$ids){... on ProductVariant{id title sku availableForSale inventoryQuantity product{id title status}}}}""", {"input": draft_input, "ids": variant_ids})
        payload = result["data"]["draftOrderCalculate"]
        if payload.get("userErrors"):
            raise ShopifyError("Shopify rejeitou o cálculo do draft order", details=payload["userErrors"])
        variants = {node["id"]: node for node in result["data"]["nodes"] if node is not None}
        missing = sorted(set(variant_ids) - set(variants))
        if missing:
            raise ShopifyError("Variantes não encontradas", details={"invalidIds": missing})
        inactive = [node for node in variants.values() if node["product"]["status"] not in {"ACTIVE", "UNLISTED"}]
        warnings = []
        if inactive:
            warnings.append("Há variantes de produtos não ativos no draft order.")
        unavailable = [node for node in variants.values() if not node["availableForSale"]]
        if unavailable:
            warnings.append("Há variantes indisponíveis; a criação não garante reserva de estoque.")
        mutation_args = {"input": draft_input}
        token = self.confirmations.issue("shopify_create_draft_order", mutation_args)
        return {"calculatedDraftOrder": payload["calculatedDraftOrder"], "variants": list(variants.values()), "warnings": warnings, **token}

    async def create_draft_order(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"input": self._draft_order_input(args)}
        self._require_write(args, "shopify_create_draft_order", mutation_args)
        query = """mutation DraftOrderCreate($input:DraftOrderInput!){draftOrderCreate(input:$input){draftOrder{id name status createdAt invoiceUrl email currencyCode totalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} customer{id displayName email} lineItems(first:250){nodes{id name sku quantity variant{id title sku}}} discountCodes{code applicable rejectionReason}} userErrors{field message}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "draftOrderCreate", **mutation_result(result, "draftOrderCreate")}

    @staticmethod
    def _invoice_args(args: dict[str, Any]) -> dict[str, Any]:
        value = {"id": args["id"]}
        if args.get("email") is not None:
            value["email"] = args["email"]
        return value

    async def prepare_draft_order_invoice_send(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = self._invoice_args(args)
        result = await self.client.graphql("""mutation DraftOrderInvoicePreview($id:ID!,$email:EmailInput){draftOrderInvoicePreview(id:$id,email:$email){previewHtml previewSubject userErrors{field message}} draftOrder:draftOrder(id:$id){id name status email invoiceSentAt totalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}}}}""", {"id": args["id"], "email": args.get("email")})
        payload = result["data"]["draftOrderInvoicePreview"]
        if payload.get("userErrors"):
            raise ShopifyError("Shopify rejeitou o preview da invoice", details=payload["userErrors"])
        draft = result["data"]["draftOrder"]
        if draft is None:
            raise ShopifyError("Draft order não encontrado")
        token = self.confirmations.issue("shopify_send_draft_order_invoice", mutation_args)
        return {"draftOrder": draft, "recipient": (args.get("email") or {}).get("to") or draft.get("email"), "previewSubject": payload.get("previewSubject"), "previewHtml": payload.get("previewHtml"), "externalEffect": True, "warnings": ["A execução enviará email real ao destinatário exibido."], **token}

    async def send_draft_order_invoice(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = self._invoice_args(args)
        self._require_write(args, "shopify_send_draft_order_invoice", mutation_args)
        result = await self.client.graphql("""mutation DraftOrderInvoiceSend($id:ID!,$email:EmailInput){draftOrderInvoiceSend(id:$id,email:$email){draftOrder{id name status invoiceSentAt email} userErrors{field message}}}""", {"id": args["id"], "email": args.get("email")})
        return {"success": True, "operation": "draftOrderInvoiceSend", **mutation_result(result, "draftOrderInvoiceSend")}

    @staticmethod
    def _draft_complete_args(args: dict[str, Any]) -> dict[str, Any]:
        return {field: args[field] for field in ("id", "paymentGatewayId", "sourceName") if field in args}

    async def prepare_draft_order_complete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query DraftOrderCompletePreview($id:ID!){draftOrder(id:$id){id name status completedAt email currencyCode totalPriceSet{shopMoney{amount currencyCode} presentmentMoney{amount currencyCode}} lineItems(first:250){nodes{id name sku quantity variant{id sku requiresComponents availableForSale inventoryQuantity product{id title status}} components{id sku title quantity variant{id sku availableForSale inventoryQuantity}}}} order{id name}}}""", {"id": args["id"]})
        draft = result["data"]["draftOrder"]
        if draft is None:
            raise ShopifyError("Draft order não encontrado")
        if draft["status"] == "COMPLETED" or draft.get("order") is not None:
            raise ShopifyError("Draft order já foi concluído", details={"order": draft.get("order")})
        shortages = []
        for item in draft["lineItems"]["nodes"]:
            variant = item.get("variant")
            if variant and (not variant["availableForSale"] or variant["inventoryQuantity"] < item["quantity"]):
                shortages.append({"lineItemId": item["id"], "sku": item.get("sku"), "requested": item["quantity"], "inventoryQuantity": variant["inventoryQuantity"], "availableForSale": variant["availableForSale"]})
        mutation_args = self._draft_complete_args(args)
        amount = draft.get('totalPriceSet', {}).get('shopMoney', {})
        financial = self._financial('complete_draft', amount.get('amount'), amount.get('currencyCode'))
        token = self.confirmations.issue("shopify_complete_draft_order", mutation_args, context=financial)
        token['financialSummary'] = financial
        warnings = ["A conclusão converte o draft em pedido, marca pagamento e reserva estoque; não pode ser desfeita por esta tool."]
        if shortages:
            warnings.append("A Shopify poderá rejeitar ou concluir com disponibilidade insuficiente conforme a política das variantes.")
        return {"draftOrder": draft, "inventoryWarnings": shortages, "financial": True, "irreversible": True, "warnings": warnings, **token}

    async def complete_draft_order(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = self._draft_complete_args(args)
        context = self._require_write(args, "shopify_complete_draft_order", mutation_args)
        await self._recheck_financial(context, 'complete_draft', args['id'])
        result = await self.client.graphql("""mutation DraftOrderComplete($id:ID!,$paymentGatewayId:ID,$sourceName:String){draftOrderComplete(id:$id,paymentGatewayId:$paymentGatewayId,sourceName:$sourceName){draftOrder{id name status completedAt order{id name displayFinancialStatus displayFulfillmentStatus}} userErrors{field message}}}""", mutation_args)
        return {"success": True, "operation": "draftOrderComplete", **mutation_result(result, "draftOrderComplete")}

    async def prepare_draft_order_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query DraftOrderDeletePreview($id:ID!){draftOrder(id:$id){id name status completedAt invoiceSentAt email totalPriceSet{shopMoney{amount currencyCode}} order{id name}}}""", {"id": args["id"]})
        draft = result["data"]["draftOrder"]
        if draft is None:
            raise ShopifyError("Draft order não encontrado")
        if draft.get("order") is not None or draft["status"] == "COMPLETED":
            raise ShopifyError("Draft order concluído não pode ser excluído por esta operação")
        mutation_args = {"input": {"id": args["id"]}}
        token = self.confirmations.issue("shopify_delete_draft_order", mutation_args)
        return {"draftOrder": draft, "irreversible": True, "warnings": ["O draft será excluído definitivamente; invoices já recebidas podem conter links antigos."], **token}

    async def delete_draft_order(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"input": {"id": args["id"]}}
        self._require_write(args, "shopify_delete_draft_order", mutation_args)
        result = await self.client.graphql("""mutation DraftOrderDelete($input:DraftOrderDeleteInput!){draftOrderDelete(input:$input){deletedId userErrors{field message}}}""", mutation_args)
        return {"success": True, "operation": "draftOrderDelete", **mutation_result(result, "draftOrderDelete")}

    async def list_code_discounts(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"""query CodeDiscounts($first:Int!,$after:String,$query:String){{codeDiscountNodes(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){{edges{{cursor node{{id codeDiscount{{{DISCOUNT_CODE_FRAGMENTS}}}}}}}pageInfo{{hasNextPage endCursor}}}}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "codeDiscountNodes")

    async def get_code_discount(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"""query CodeDiscount($id:ID!){{codeDiscountNode(id:$id){{id codeDiscount{{{DISCOUNT_CODE_FRAGMENTS}}}}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"codeDiscountNode": result["data"]["codeDiscountNode"]}

    async def get_code_discount_by_code(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"""query CodeDiscountByCode($code:String!){{codeDiscountNodeByCode(code:$code){{id codeDiscount{{{DISCOUNT_CODE_FRAGMENTS}}}}}}}"""
        result = await self.client.graphql(query, {"code": args["code"]})
        return {"codeDiscountNode": result["data"]["codeDiscountNodeByCode"]}

    @staticmethod
    def _discount_basic_input(args: dict[str, Any]) -> dict[str, Any]:
        value: dict[str, Any] = {"title": args["title"], "code": args["code"], "startsAt": args["startsAt"], "appliesOncePerCustomer": args["appliesOncePerCustomer"], "combinesWith": args["combinesWith"]}
        if "endsAt" in args:
            value["endsAt"] = args["endsAt"]
        if "usageLimit" in args:
            value["usageLimit"] = args["usageLimit"]
        if args["audienceType"] == "ALL":
            value["context"] = {"all": "ALL"}
        elif args["audienceType"] == "CUSTOMERS":
            value["context"] = {"customers": {"add": args["customerIds"]}}
        else:
            value["context"] = {"customerSegments": {"add": args["segmentIds"]}}
        if args["targetType"] == "ALL":
            items = {"all": True}
        elif args["targetType"] == "PRODUCTS":
            items = {"products": {"productsToAdd": args["productIds"]}}
        else:
            items = {"collections": {"add": args["collectionIds"]}}
        if args["valueType"] == "PERCENTAGE":
            discount_value = {"percentage": args["percentage"]}
        else:
            discount_value = {"discountAmount": {"amount": args["fixedAmount"], "appliesOnEachItem": args.get("appliesOnEachItem", False)}}
        value["customerGets"] = {"items": items, "value": discount_value}
        if args["minimumType"] == "SUBTOTAL":
            value["minimumRequirement"] = {"subtotal": {"greaterThanOrEqualToSubtotal": args["minimumSubtotal"]}}
        elif args["minimumType"] == "QUANTITY":
            value["minimumRequirement"] = {"quantity": {"greaterThanOrEqualToQuantity": args["minimumQuantity"]}}
        return value

    @staticmethod
    def _validate_discount_basic_shape(args: dict[str, Any]) -> list[str]:
        required_by_mode = {
            "PERCENTAGE": "percentage", "FIXED_AMOUNT": "fixedAmount",
            "PRODUCTS": "productIds", "COLLECTIONS": "collectionIds",
            "CUSTOMERS": "customerIds", "SEGMENTS": "segmentIds",
            "SUBTOTAL": "minimumSubtotal", "QUANTITY": "minimumQuantity",
        }
        modes = (args["valueType"], args["targetType"], args["audienceType"], args["minimumType"])
        for mode in modes:
            field = required_by_mode.get(mode)
            if field and field not in args:
                raise ValueError(f"{mode} exige {field}")
        forbidden = {
            "PERCENTAGE": {"fixedAmount", "appliesOnEachItem"}, "FIXED_AMOUNT": {"percentage"},
            "ALL": set(), "PRODUCTS": {"collectionIds"}, "COLLECTIONS": {"productIds"},
            "CUSTOMERS": {"segmentIds"}, "SEGMENTS": {"customerIds"},
            "NONE": {"minimumSubtotal", "minimumQuantity"}, "SUBTOTAL": {"minimumQuantity"}, "QUANTITY": {"minimumSubtotal"},
        }
        for mode in modes:
            invalid = sorted(forbidden.get(mode, set()) & set(args))
            if invalid:
                raise ValueError(f"Campos incompatíveis com {mode}: {', '.join(invalid)}")
        if args.get("endsAt") is not None:
            starts = datetime.fromisoformat(args["startsAt"].replace("Z", "+00:00"))
            ends = datetime.fromisoformat(args["endsAt"].replace("Z", "+00:00"))
            if ends <= starts:
                raise ValueError("endsAt deve ser posterior a startsAt")
        ids = []
        for field in ("productIds", "collectionIds", "customerIds", "segmentIds"):
            ids.extend(args.get(field, []))
        return ids

    async def prepare_discount_code_basic_create(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = self._validate_discount_basic_shape(args)
        result = await self.client.graphql("""query DiscountBasicPreview($code:String!,$ids:[ID!]!){codeDiscountNodeByCode(code:$code){id codeDiscount{__typename ... on DiscountCodeBasic{title status}}} nodes(ids:$ids){__typename ... on Product{id title status} ... on Collection{id title} ... on Customer{id displayName email} ... on Segment{id name}}}""", {"code": args["code"], "ids": ids})
        if result["data"]["codeDiscountNodeByCode"] is not None:
            raise ShopifyError("Código de desconto já existe", details={"existing": result["data"]["codeDiscountNodeByCode"]})
        found = {node["id"]: node for node in result["data"]["nodes"] if node is not None}
        missing = sorted(set(ids) - set(found))
        if missing:
            raise ShopifyError("GIDs de público ou alvo não encontrados", details={"invalidIds": missing})
        discount_input = self._discount_basic_input(args)
        mutation_args = {"basicCodeDiscount": discount_input}
        token = self.confirmations.issue("shopify_create_discount_code_basic", mutation_args)
        return {"code": args["code"], "resolvedTargets": list(found.values()), "shopifyInput": discount_input, "warnings": ["A Shopify avaliará elegibilidade, combinações e limites novamente em cada checkout."], **token}

    async def create_discount_code_basic(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_discount_basic_shape(args)
        mutation_args = {"basicCodeDiscount": self._discount_basic_input(args)}
        self._require_write(args, "shopify_create_discount_code_basic", mutation_args)
        query = """mutation DiscountCodeBasicCreate($basicCodeDiscount:DiscountCodeBasicInput!){discountCodeBasicCreate(basicCodeDiscount:$basicCodeDiscount){codeDiscountNode{id codeDiscount{... on DiscountCodeBasic{title status startsAt endsAt summary appliesOncePerCustomer usageLimit codes(first:20){nodes{id code}} customerGets{value{... on DiscountPercentage{percentage} ... on DiscountAmount{amount{amount currencyCode} appliesOnEachItem}}}}}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "discountCodeBasicCreate", **mutation_result(result, "discountCodeBasicCreate")}

    async def _discount_lifecycle_preview(self, discount_id: str) -> dict[str, Any]:
        result = await self.client.graphql(f"""query DiscountLifecycle($id:ID!){{codeDiscountNode(id:$id){{id codeDiscount{{{DISCOUNT_CODE_FRAGMENTS}}}}}}}""", {"id": discount_id})
        node = result["data"]["codeDiscountNode"]
        if node is None:
            raise ShopifyError("Cupom não encontrado")
        return node

    async def prepare_discount_code_status_change(self, args: dict[str, Any]) -> dict[str, Any]:
        node = await self._discount_lifecycle_preview(args["id"])
        current = node["codeDiscount"].get("status")
        desired = "ACTIVE" if args["action"] == "ACTIVATE" else "EXPIRED"
        mutation_args = {"id": args["id"], "action": args["action"]}
        token = self.confirmations.issue("shopify_set_discount_code_status", mutation_args)
        warnings = []
        if args["action"] == "ACTIVATE":
            warnings.append("Ativar pode mover startsAt para agora e remover endsAt quando o cupom estiver expirado.")
        else:
            warnings.append("Desativar altera a vigência para agora e impede novos usos; o cupom permanece armazenado.")
        return {"discount": node, "beforeStatus": current, "expectedStatus": desired, "willChange": current != desired, "warnings": warnings, **token}

    async def set_discount_code_status(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "action": args["action"]}
        self._require_write(args, "shopify_set_discount_code_status", mutation_args)
        field = "discountCodeActivate" if args["action"] == "ACTIVATE" else "discountCodeDeactivate"
        query = f"""mutation DiscountCodeStatus($id:ID!){{{field}(id:$id){{codeDiscountNode{{id codeDiscount{{__typename ... on DiscountCodeBasic{{title status startsAt endsAt}} ... on DiscountCodeBxgy{{title status startsAt endsAt}} ... on DiscountCodeFreeShipping{{title status startsAt endsAt}} ... on DiscountCodeApp{{title status startsAt endsAt}}}}}} userErrors{{field message code}}}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"success": True, "operation": field, **mutation_result(result, field)}

    async def prepare_discount_code_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        node = await self._discount_lifecycle_preview(args["id"])
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_delete_discount_code", mutation_args)
        return {"discount": node, "irreversible": True, "warnings": ["A exclusão é permanente. Prefira desativar quando histórico e possível reativação forem importantes."], **token}

    async def delete_discount_code(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_delete_discount_code", mutation_args)
        result = await self.client.graphql("""mutation DiscountCodeDelete($id:ID!){discountCodeDelete(id:$id){deletedCodeDiscountId userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "discountCodeDelete", **mutation_result(result, "discountCodeDelete")}

    @staticmethod
    def _page_input(args: dict[str, Any]) -> dict[str, Any]:
        fields = ("title", "handle", "body", "isPublished", "publishDate", "templateSuffix", "redirectNewHandle")
        return {field: args[field] for field in fields if field in args}

    @staticmethod
    def _validate_page_input(page: dict[str, Any]) -> None:
        if page.get("publishDate") is not None and page.get("isPublished") is False:
            raise ValueError("publishDate não pode ser combinado com isPublished=false")
        if "redirectNewHandle" in page and "handle" not in page:
            raise ValueError("redirectNewHandle exige alteração de handle")

    async def list_pages(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Pages($first:Int!,$after:String,$query:String){pages(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){edges{cursor node{id title handle bodySummary isPublished publishedAt createdAt updatedAt templateSuffix seo{title description}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "pages")

    async def get_page(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query Page($id:ID!){page(id:$id){id title handle body bodySummary isPublished publishedAt createdAt updatedAt templateSuffix seo{title description}}}""", {"id": args["id"]})
        return {"page": result["data"]["page"]}

    async def prepare_page_create(self, args: dict[str, Any]) -> dict[str, Any]:
        page = self._page_input(args)
        self._validate_page_input(page)
        duplicate = None
        if args.get("handle"):
            result = await self.client.graphql("""query PageHandlePreview($query:String!){pages(first:2,query:$query){nodes{id title handle isPublished}}}""", {"query": _search_exact("handle", args["handle"])})
            matches = [item for item in result["data"]["pages"]["nodes"] if item["handle"] == args["handle"]]
            duplicate = matches[0] if matches else None
        if duplicate:
            raise ShopifyError("Handle de página já existe", details={"existing": duplicate})
        mutation_args = {"page": page}
        token = self.confirmations.issue("shopify_create_page", mutation_args)
        warnings = []
        if args["isPublished"]:
            warnings.append("A página ficará visível na loja conforme a data de publicação.")
        if args.get("body"):
            warnings.append("O HTML será armazenado e renderizado pela loja; revise links, scripts e conteúdo externo.")
        return {"page": page, "warnings": warnings, **token}

    async def create_page(self, args: dict[str, Any]) -> dict[str, Any]:
        page = self._page_input(args)
        self._validate_page_input(page)
        mutation_args = {"page": page}
        self._require_write(args, "shopify_create_page", mutation_args)
        result = await self.client.graphql("""mutation PageCreate($page:PageCreateInput!){pageCreate(page:$page){page{id title handle bodySummary isPublished publishedAt templateSuffix} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "pageCreate", **mutation_result(result, "pageCreate")}

    async def prepare_page_update(self, args: dict[str, Any]) -> dict[str, Any]:
        page = self._page_input(args)
        if not page:
            raise ValueError("Informe ao menos um campo da página para alterar")
        self._validate_page_input(page)
        result = await self.client.graphql("""query PageUpdatePreview($id:ID!){page(id:$id){id title handle body isPublished publishedAt templateSuffix}}""", {"id": args["id"]})
        current = result["data"]["page"]
        if current is None:
            raise ShopifyError("Página não encontrada")
        comparable = {key: value for key, value in page.items() if key != "redirectNewHandle"}
        before = {key: current.get("publishedAt" if key == "publishDate" else key) for key in comparable}
        mutation_args = {"id": args["id"], "page": page}
        token = self.confirmations.issue("shopify_update_page", mutation_args)
        warnings = []
        if page.get("redirectNewHandle"):
            warnings.append("A Shopify criará redirect do handle anterior.")
        if page.get("isPublished") is True and not current["isPublished"]:
            warnings.append("A página passará a ficar visível na loja.")
        return {"page": {"id": current["id"], "title": current["title"]}, "before": before, "after": comparable, "warnings": warnings, **token}

    async def update_page(self, args: dict[str, Any]) -> dict[str, Any]:
        page = self._page_input(args)
        if not page:
            raise ValueError("Informe ao menos um campo da página para alterar")
        self._validate_page_input(page)
        mutation_args = {"id": args["id"], "page": page}
        self._require_write(args, "shopify_update_page", mutation_args)
        result = await self.client.graphql("""mutation PageUpdate($id:ID!,$page:PageUpdateInput!){pageUpdate(id:$id,page:$page){page{id title handle bodySummary isPublished publishedAt templateSuffix} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "pageUpdate", **mutation_result(result, "pageUpdate")}

    async def prepare_page_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query PageDeletePreview($id:ID!){page(id:$id){id title handle bodySummary isPublished publishedAt updatedAt}}""", {"id": args["id"]})
        page = result["data"]["page"]
        if page is None:
            raise ShopifyError("Página não encontrada")
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_delete_page", mutation_args)
        return {"page": page, "irreversible": True, "warnings": ["A exclusão é permanente e pode quebrar menus e links externos."], **token}

    async def delete_page(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_delete_page", mutation_args)
        result = await self.client.graphql("""mutation PageDelete($id:ID!){pageDelete(id:$id){deletedPageId userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "pageDelete", **mutation_result(result, "pageDelete")}

    @staticmethod
    def _validate_redirect(path: str, target: str) -> None:
        normalized_path = path.rstrip("/") or "/"
        normalized_target = target.rstrip("/") or "/"
        if normalized_path == normalized_target:
            raise ValueError("Redirect não pode apontar para o próprio caminho")

    async def list_url_redirects(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query UrlRedirects($first:Int!,$after:String,$query:String){urlRedirects(first:$first,after:$after,query:$query){edges{cursor node{id path target}}pageInfo{hasNextPage endCursor}}}""", {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "urlRedirects")

    async def get_url_redirect(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query UrlRedirect($id:ID!){urlRedirect(id:$id){id path target}}""", {"id": args["id"]})
        return {"urlRedirect": result["data"]["urlRedirect"]}

    async def _redirect_conflict(self, path: str, *, exclude_id: str | None = None) -> dict[str, Any] | None:
        result = await self.client.graphql("""query UrlRedirectPath($query:String!){urlRedirects(first:10,query:$query){nodes{id path target}}}""", {"query": _search_exact("path", path)})
        return next((item for item in result["data"]["urlRedirects"]["nodes"] if item["path"] == path and item["id"] != exclude_id), None)

    async def prepare_url_redirect_create(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_redirect(args["path"], args["target"])
        conflict = await self._redirect_conflict(args["path"])
        if conflict:
            raise ShopifyError("Já existe redirect para este caminho", details={"existing": conflict})
        mutation_args = {"urlRedirect": {"path": args["path"], "target": args["target"]}}
        token = self.confirmations.issue("shopify_create_url_redirect", mutation_args)
        return {"redirect": mutation_args["urlRedirect"], "warnings": ["Loops indiretos entre múltiplos redirects devem ser revisados pelo agente."], **token}

    async def create_url_redirect(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_redirect(args["path"], args["target"])
        mutation_args = {"urlRedirect": {"path": args["path"], "target": args["target"]}}
        self._require_write(args, "shopify_create_url_redirect", mutation_args)
        result = await self.client.graphql("""mutation UrlRedirectCreate($urlRedirect:UrlRedirectInput!){urlRedirectCreate(urlRedirect:$urlRedirect){urlRedirect{id path target} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "urlRedirectCreate", **mutation_result(result, "urlRedirectCreate")}

    async def prepare_url_redirect_update(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_redirect(args["path"], args["target"])
        current_result = await self.client.graphql("""query UrlRedirectUpdatePreview($id:ID!){urlRedirect(id:$id){id path target}}""", {"id": args["id"]})
        current = current_result["data"]["urlRedirect"]
        if current is None:
            raise ShopifyError("Redirect não encontrado")
        conflict = await self._redirect_conflict(args["path"], exclude_id=args["id"])
        if conflict:
            raise ShopifyError("Outro redirect já usa este caminho", details={"existing": conflict})
        mutation_args = {"id": args["id"], "urlRedirect": {"path": args["path"], "target": args["target"]}}
        token = self.confirmations.issue("shopify_update_url_redirect", mutation_args)
        return {"before": current, "after": mutation_args["urlRedirect"], "willChange": current["path"] != args["path"] or current["target"] != args["target"], **token}

    async def update_url_redirect(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_redirect(args["path"], args["target"])
        mutation_args = {"id": args["id"], "urlRedirect": {"path": args["path"], "target": args["target"]}}
        self._require_write(args, "shopify_update_url_redirect", mutation_args)
        result = await self.client.graphql("""mutation UrlRedirectUpdate($id:ID!,$urlRedirect:UrlRedirectInput!){urlRedirectUpdate(id:$id,urlRedirect:$urlRedirect){urlRedirect{id path target} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "urlRedirectUpdate", **mutation_result(result, "urlRedirectUpdate")}

    async def prepare_url_redirect_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query UrlRedirectDeletePreview($id:ID!){urlRedirect(id:$id){id path target}}""", {"id": args["id"]})
        redirect = result["data"]["urlRedirect"]
        if redirect is None:
            raise ShopifyError("Redirect não encontrado")
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_delete_url_redirect", mutation_args)
        return {"redirect": redirect, "irreversible": True, "warnings": ["O caminho antigo deixará de redirecionar imediatamente."], **token}

    async def delete_url_redirect(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_delete_url_redirect", mutation_args)
        result = await self.client.graphql("""mutation UrlRedirectDelete($id:ID!){urlRedirectDelete(id:$id){deletedUrlRedirectId userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "urlRedirectDelete", **mutation_result(result, "urlRedirectDelete")}

    @staticmethod
    def _menu_resource_ids(items: list[dict[str, Any]]) -> list[str]:
        expected = {"ARTICLE": "Article", "BLOG": "Blog", "COLLECTION": "Collection", "METAOBJECT": "Metaobject", "PAGE": "Page", "PRODUCT": "Product"}
        ids: list[str] = []
        item_ids: list[str] = []
        def visit(nodes: list[dict[str, Any]], depth: int) -> None:
            if depth > 3:
                raise ValueError("Menu aceita no máximo três níveis")
            for item in nodes:
                resource_id = item.get("resourceId")
                if item["type"] in expected and not resource_id:
                    raise ValueError(f"Item {item['type']} exige resourceId")
                if item["type"] not in expected and resource_id:
                    raise ValueError(f"Item {item['type']} não aceita resourceId")
                if resource_id:
                    actual = resource_id.split("/")[3]
                    if actual != expected[item["type"]]:
                        raise ValueError(f"resourceId incompatível com tipo {item['type']}")
                    ids.append(resource_id)
                if item.get("id"):
                    item_ids.append(item["id"])
                visit(item.get("items", []), depth + 1)
        visit(items, 1)
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Cada MenuItem ID pode aparecer apenas uma vez")
        return ids

    async def list_menus(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Menus($first:Int!,$after:String,$query:String){menus(first:$first,after:$after,query:$query){edges{cursor node{id title handle isDefault items{ id title type url resourceId tags items{id title type url resourceId tags items{id title type url resourceId tags}}}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "menus")

    async def get_menu(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Menu($id:ID!){menu(id:$id){id title handle isDefault items{id title type url resourceId tags items{id title type url resourceId tags items{id title type url resourceId tags}}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"menu": result["data"]["menu"]}

    async def _validate_menu_resources(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ids = self._menu_resource_ids(items)
        if not ids:
            return []
        result = await self.client.graphql("""query MenuResources($ids:[ID!]!){nodes(ids:$ids){id __typename}}""", {"ids": ids})
        found = {node["id"]: node for node in result["data"]["nodes"] if node is not None}
        missing = sorted(set(ids) - set(found))
        if missing:
            raise ShopifyError("Recursos do menu não encontrados", details={"invalidIds": missing})
        return list(found.values())

    async def prepare_menu_create(self, args: dict[str, Any]) -> dict[str, Any]:
        resources = await self._validate_menu_resources(args["items"])
        result = await self.client.graphql("""query MenuHandle($query:String!){menus(first:10,query:$query){nodes{id title handle isDefault}}}""", {"query": args["handle"]})
        duplicate = next((menu for menu in result["data"]["menus"]["nodes"] if menu["handle"] == args["handle"]), None)
        if duplicate:
            raise ShopifyError("Handle de menu já existe", details={"existing": duplicate})
        mutation_args = {"title": args["title"], "handle": args["handle"], "items": args["items"]}
        token = self.confirmations.issue("shopify_create_menu", mutation_args)
        return {"menu": mutation_args, "resolvedResources": resources, "warnings": ["A criação não associa automaticamente o menu a um tema."], **token}

    async def create_menu(self, args: dict[str, Any]) -> dict[str, Any]:
        self._menu_resource_ids(args["items"])
        mutation_args = {"title": args["title"], "handle": args["handle"], "items": args["items"]}
        self._require_write(args, "shopify_create_menu", mutation_args)
        result = await self.client.graphql("""mutation MenuCreate($title:String!,$handle:String!,$items:[MenuItemCreateInput!]!){menuCreate(title:$title,handle:$handle,items:$items){menu{id title handle isDefault items{id title type url resourceId}} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "menuCreate", **mutation_result(result, "menuCreate")}

    async def prepare_menu_update(self, args: dict[str, Any]) -> dict[str, Any]:
        resources = await self._validate_menu_resources(args["items"])
        result = await self.client.graphql("""query MenuUpdatePreview($id:ID!){menu(id:$id){id title handle isDefault items{id title type url resourceId tags items{id title type url resourceId tags items{id title type url resourceId tags}}}}}""", {"id": args["id"]})
        current = result["data"]["menu"]
        if current is None:
            raise ShopifyError("Menu não encontrado")
        if current["isDefault"] and args.get("handle") and args["handle"] != current["handle"]:
            raise ShopifyError("Handle de menu padrão não pode ser alterado")
        mutation_args = {"id": args["id"], "title": args["title"], "items": args["items"]}
        if "handle" in args:
            mutation_args["handle"] = args["handle"]
        token = self.confirmations.issue("shopify_update_menu", mutation_args)
        return {"before": current, "after": mutation_args, "resolvedResources": resources, "warnings": ["items substitui integralmente a árvore e sua ordem atuais."], **token}

    async def update_menu(self, args: dict[str, Any]) -> dict[str, Any]:
        self._menu_resource_ids(args["items"])
        mutation_args = {"id": args["id"], "title": args["title"], "items": args["items"]}
        if "handle" in args:
            mutation_args["handle"] = args["handle"]
        self._require_write(args, "shopify_update_menu", mutation_args)
        result = await self.client.graphql("""mutation MenuUpdate($id:ID!,$title:String!,$handle:String,$items:[MenuItemUpdateInput!]!){menuUpdate(id:$id,title:$title,handle:$handle,items:$items){menu{id title handle isDefault items{id title type url resourceId}} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "menuUpdate", **mutation_result(result, "menuUpdate")}

    async def prepare_menu_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query MenuDeletePreview($id:ID!){menu(id:$id){id title handle isDefault items{id title url}}}""", {"id": args["id"]})
        menu = result["data"]["menu"]
        if menu is None:
            raise ShopifyError("Menu não encontrado")
        if menu["isDefault"]:
            raise ShopifyError("Menu padrão não pode ser excluído")
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_delete_menu", mutation_args)
        return {"menu": menu, "irreversible": True, "warnings": ["Temas que referenciam este menu podem ficar sem navegação."], **token}

    async def delete_menu(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_delete_menu", mutation_args)
        result = await self.client.graphql("""mutation MenuDelete($id:ID!){menuDelete(id:$id){deletedMenuId userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "menuDelete", **mutation_result(result, "menuDelete")}

    @staticmethod
    def _blog_input(args: dict[str, Any]) -> dict[str, Any]:
        return {field: args[field] for field in ("title", "handle", "templateSuffix", "commentPolicy") if field in args}

    async def list_blogs(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query Blogs($first:Int!,$after:String,$query:String){blogs(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){edges{cursor node{id title handle commentPolicy templateSuffix tags createdAt updatedAt feed{path location}}}pageInfo{hasNextPage endCursor}}}""", {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "blogs")

    async def get_blog(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query Blog($id:ID!,$first:Int!,$after:String){blog(id:$id){id title handle commentPolicy templateSuffix tags createdAt updatedAt feed{path location} articles(first:$first,after:$after,sortKey:PUBLISHED_AT,reverse:true){edges{cursor node{id title handle isPublished publishedAt updatedAt author{name} tags image{url altText}}}pageInfo{hasNextPage endCursor}}}}""", {"id": args["id"], "first": _page_size(args.get("first")), "after": args.get("after")})
        blog = result["data"]["blog"]
        if blog is None:
            return {"blog": None, "articles": [], "pageInfo": {}}
        articles = _connection(blog, "articles")
        return {"blog": {key: value for key, value in blog.items() if key != "articles"}, "articles": articles["items"], "pageInfo": articles["pageInfo"]}

    async def prepare_blog_create(self, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("handle"):
            result = await self.client.graphql("""query BlogHandle($query:String!){blogs(first:10,query:$query){nodes{id title handle}}}""", {"query": _search_exact("handle", args["handle"])})
            duplicate = next((item for item in result["data"]["blogs"]["nodes"] if item["handle"] == args["handle"]), None)
            if duplicate:
                raise ShopifyError("Handle de blog já existe", details={"existing": duplicate})
        mutation_args = {"blog": self._blog_input(args)}
        token = self.confirmations.issue("shopify_create_blog", mutation_args)
        return {"blog": mutation_args["blog"], "warnings": ["O blog será criado vazio e não é adicionado automaticamente a menus."], **token}

    async def create_blog(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"blog": self._blog_input(args)}
        self._require_write(args, "shopify_create_blog", mutation_args)
        result = await self.client.graphql("""mutation BlogCreate($blog:BlogCreateInput!){blogCreate(blog:$blog){blog{id title handle commentPolicy templateSuffix} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "blogCreate", **mutation_result(result, "blogCreate")}

    async def prepare_blog_update(self, args: dict[str, Any]) -> dict[str, Any]:
        blog_input = self._blog_input(args)
        if not blog_input:
            raise ValueError("Informe ao menos um campo do blog para alterar")
        result = await self.client.graphql("""query BlogUpdatePreview($id:ID!){blog(id:$id){id title handle commentPolicy templateSuffix updatedAt}}""", {"id": args["id"]})
        current = result["data"]["blog"]
        if current is None:
            raise ShopifyError("Blog não encontrado")
        mutation_args = {"id": args["id"], "blog": blog_input}
        token = self.confirmations.issue("shopify_update_blog", mutation_args)
        return {"before": {key: current.get(key) for key in blog_input}, "after": blog_input, "warnings": ["Alterar o handle pode quebrar links; o contrato de blog não oferece redirect automático."], **token}

    async def update_blog(self, args: dict[str, Any]) -> dict[str, Any]:
        blog_input = self._blog_input(args)
        if not blog_input:
            raise ValueError("Informe ao menos um campo do blog para alterar")
        mutation_args = {"id": args["id"], "blog": blog_input}
        self._require_write(args, "shopify_update_blog", mutation_args)
        result = await self.client.graphql("""mutation BlogUpdate($id:ID!,$blog:BlogUpdateInput!){blogUpdate(id:$id,blog:$blog){blog{id title handle commentPolicy templateSuffix} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "blogUpdate", **mutation_result(result, "blogUpdate")}

    async def prepare_blog_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query BlogDeletePreview($id:ID!){blog(id:$id){id title handle articles(first:10){nodes{id title handle isPublished publishedAt} pageInfo{hasNextPage endCursor}}}}""", {"id": args["id"]})
        blog = result["data"]["blog"]
        if blog is None:
            raise ShopifyError("Blog não encontrado")
        articles = blog["articles"]["nodes"]
        if articles and not args["allowDeleteWithArticles"]:
            raise ShopifyError("Blog contém artigos; confirme allowDeleteWithArticles=true somente após revisar a lista", details={"articles": articles, "hasMore": blog["articles"]["pageInfo"]["hasNextPage"]})
        mutation_args = {"id": args["id"], "allowDeleteWithArticles": args["allowDeleteWithArticles"]}
        token = self.confirmations.issue("shopify_delete_blog", mutation_args)
        return {"blog": blog, "irreversible": True, "warnings": ["A exclusão é permanente e pode afetar artigos, menus e URLs vinculados."], **token}

    async def delete_blog(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "allowDeleteWithArticles": args["allowDeleteWithArticles"]}
        self._require_write(args, "shopify_delete_blog", mutation_args)
        result = await self.client.graphql("""mutation BlogDelete($id:ID!){blogDelete(id:$id){deletedBlogId userErrors{field message code}}}""", {"id": args["id"]})
        return {"success": True, "operation": "blogDelete", **mutation_result(result, "blogDelete")}

    @staticmethod
    def _article_input(args: dict[str, Any]) -> dict[str, Any]:
        mapping = {"blogId": "blogId", "title": "title", "handle": "handle", "body": "body", "summary": "summary", "isPublished": "isPublished", "publishDate": "publishDate", "tags": "tags", "templateSuffix": "templateSuffix", "image": "image", "redirectNewHandle": "redirectNewHandle"}
        value = {target: args[source] for source, target in mapping.items() if source in args}
        if "authorName" in args:
            value["author"] = {"name": args["authorName"]}
        return value

    @staticmethod
    def _validate_article_input(value: dict[str, Any]) -> None:
        if value.get("publishDate") is not None and value.get("isPublished") is False:
            raise ValueError("publishDate não pode ser combinado com isPublished=false")
        if "redirectNewHandle" in value and "handle" not in value:
            raise ValueError("redirectNewHandle exige alteração de handle")

    async def list_articles(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query Articles($first:Int!,$after:String,$query:String){articles(first:$first,after:$after,query:$query,sortKey:PUBLISHED_AT,reverse:true){edges{cursor node{id title handle isPublished publishedAt createdAt updatedAt author{name} blog{id title handle} tags summary image{url altText}}}pageInfo{hasNextPage endCursor}}}""", {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "articles")

    async def get_article(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query Article($id:ID!){article(id:$id){id title handle body summary isPublished publishedAt createdAt updatedAt templateSuffix author{name} blog{id title handle} tags image{url altText width height} commentsCount{count}}}""", {"id": args["id"]})
        return {"article": result["data"]["article"]}

    async def prepare_article_create(self, args: dict[str, Any]) -> dict[str, Any]:
        article = self._article_input(args)
        self._validate_article_input(article)
        result = await self.client.graphql("""query ArticleCreatePreview($blogId:ID!,$query:String){blog(id:$blogId){id title handle commentPolicy} articles(first:10,query:$query){nodes{id title handle blog{id}}}}""", {"blogId": args["blogId"], "query": _search_exact("handle", args["handle"]) if args.get("handle") else None})
        blog = result["data"]["blog"]
        if blog is None:
            raise ShopifyError("Blog não encontrado")
        if args.get("handle"):
            duplicate = next((item for item in result["data"]["articles"]["nodes"] if item["handle"] == args["handle"] and item["blog"]["id"] == args["blogId"]), None)
            if duplicate:
                raise ShopifyError("Handle de artigo já existe neste blog", details={"existing": duplicate})
        mutation_args = {"article": article}
        token = self.confirmations.issue("shopify_create_article", mutation_args)
        warnings = ["Revise HTML, links e imagem externa antes de aplicar."]
        if args["isPublished"]:
            warnings.append("O artigo ficará visível conforme publishDate.")
        return {"blog": blog, "article": article, "warnings": warnings, **token}

    async def create_article(self, args: dict[str, Any]) -> dict[str, Any]:
        article = self._article_input(args)
        self._validate_article_input(article)
        mutation_args = {"article": article}
        self._require_write(args, "shopify_create_article", mutation_args)
        result = await self.client.graphql("""mutation ArticleCreate($article:ArticleCreateInput!){articleCreate(article:$article){article{id title handle isPublished publishedAt author{name} blog{id title handle} tags image{url altText}} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "articleCreate", **mutation_result(result, "articleCreate")}

    async def prepare_article_update(self, args: dict[str, Any]) -> dict[str, Any]:
        article = self._article_input(args)
        if not article:
            raise ValueError("Informe ao menos um campo do artigo para alterar")
        self._validate_article_input(article)
        result = await self.client.graphql("""query ArticleUpdatePreview($id:ID!){article(id:$id){id title handle body summary isPublished publishedAt templateSuffix author{name} blog{id title handle} tags image{url altText}}}""", {"id": args["id"]})
        current = result["data"]["article"]
        if current is None:
            raise ShopifyError("Artigo não encontrado")
        if args.get("blogId") and args["blogId"] != current["blog"]["id"]:
            target = await self.client.graphql("""query ArticleTargetBlog($id:ID!){blog(id:$id){id title handle}}""", {"id": args["blogId"]})
            if target["data"]["blog"] is None:
                raise ShopifyError("Blog de destino não encontrado")
        mutation_args = {"id": args["id"], "article": article}
        token = self.confirmations.issue("shopify_update_article", mutation_args)
        return {"before": current, "after": article, "warnings": ["Campos enviados alteram conteúdo e publicação; tags substitui a lista atual."], **token}

    async def update_article(self, args: dict[str, Any]) -> dict[str, Any]:
        article = self._article_input(args)
        if not article:
            raise ValueError("Informe ao menos um campo do artigo para alterar")
        self._validate_article_input(article)
        mutation_args = {"id": args["id"], "article": article}
        self._require_write(args, "shopify_update_article", mutation_args)
        result = await self.client.graphql("""mutation ArticleUpdate($id:ID!,$article:ArticleUpdateInput!){articleUpdate(id:$id,article:$article){article{id title handle isPublished publishedAt author{name} blog{id title handle} tags image{url altText}} userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "articleUpdate", **mutation_result(result, "articleUpdate")}

    async def prepare_article_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query ArticleDeletePreview($id:ID!){article(id:$id){id title handle isPublished publishedAt updatedAt blog{id title handle}}}""", {"id": args["id"]})
        article = result["data"]["article"]
        if article is None:
            raise ShopifyError("Artigo não encontrado")
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_delete_article", mutation_args)
        return {"article": article, "irreversible": True, "warnings": ["A exclusão remove permanentemente conteúdo, metadados e URL do artigo."], **token}

    async def delete_article(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_delete_article", mutation_args)
        result = await self.client.graphql("""mutation ArticleDelete($id:ID!){articleDelete(id:$id){deletedArticleId userErrors{field message code}}}""", mutation_args)
        return {"success": True, "operation": "articleDelete", **mutation_result(result, "articleDelete")}

    async def list_customers(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Customers($first:Int!,$after:String,$query:String){customers(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){edges{cursor node{id displayName firstName lastName email phone state tags numberOfOrders amountSpent{amount currencyCode} createdAt updatedAt defaultAddress{city provinceCode countryCodeV2}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "customers")

    async def get_customer(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Customer($id:ID!,$first:Int!,$after:String){customer(id:$id){id displayName firstName lastName email phone state locale note tags taxExempt taxExemptions verifiedEmail numberOfOrders amountSpent{amount currencyCode} lifetimeDuration createdAt updatedAt defaultAddress{id name company address1 address2 city provinceCode zip countryCodeV2 phone} addressesV2(first:100){nodes{id name company address1 address2 city provinceCode zip countryCodeV2 phone}} emailMarketingConsent{marketingState marketingOptInLevel consentUpdatedAt} smsMarketingConsent{marketingState marketingOptInLevel consentUpdatedAt} orders(first:$first,after:$after,sortKey:PROCESSED_AT,reverse:true){edges{cursor node{id name processedAt displayFinancialStatus displayFulfillmentStatus currentTotalPriceSet{shopMoney{amount currencyCode}}}}pageInfo{hasNextPage endCursor}}}}"""
        result = await self.client.graphql(query, {"id": args["id"], "first": _page_size(args.get("first")), "after": args.get("after")})
        customer = result["data"]["customer"]
        if customer is None:
            return {"customer": None, "orders": [], "pageInfo": {}}
        orders = _connection(customer, "orders")
        return {"customer": {key: value for key, value in customer.items() if key != "orders"}, "orders": orders["items"], "pageInfo": orders["pageInfo"], "containsPII": True}

    async def count_customers(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query CustomersCount($query:String,$limit:Int){customersCount(query:$query,limit:$limit){count precision}}"""
        result = await self.client.graphql(query, {"query": args.get("query"), "limit": args.get("limit", 10000)})
        return {"customersCount": result["data"]["customersCount"]}

    async def list_collections(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Collections($first:Int!,$after:String,$query:String){collections(first:$first,after:$after,query:$query,sortKey:UPDATED_AT,reverse:true){edges{cursor node{id title handle description updatedAt sortOrder seo{title description} productsCount{count}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "collections")

    async def get_collection(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Collection($id:ID!){collection(id:$id){id title handle description descriptionHtml updatedAt sortOrder templateSuffix seo{title description} image{id url altText width height} productsCount{count precision} ruleSet{appliedDisjunctively rules{column relation condition}}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"collection": result["data"]["collection"]}

    async def get_collection_by_handle(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query CollectionByHandle($identifier:CollectionIdentifierInput!){collectionByIdentifier(identifier:$identifier){id title handle description descriptionHtml updatedAt sortOrder templateSuffix seo{title description} image{id url altText width height} productsCount{count precision} ruleSet{appliedDisjunctively rules{column relation condition}}}}"""
        result = await self.client.graphql(query, {"identifier": {"handle": args["handle"]}})
        return {"collection": result["data"]["collectionByIdentifier"]}

    async def list_collection_products(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query CollectionProducts($id:ID!,$first:Int!,$after:String){collection(id:$id){id title handle ruleSet{appliedDisjunctively} products(first:$first,after:$after){edges{cursor node{id title handle status vendor productType totalInventory updatedAt}}pageInfo{hasNextPage endCursor}}}}"""
        result = await self.client.graphql(query, {"id": args["id"], "first": _page_size(args.get("first")), "after": args.get("after")})
        collection = result["data"]["collection"]
        if collection is None:
            return {"collection": None, "items": [], "pageInfo": {}}
        products = _connection(collection, "products")
        return {"collection": {"id": collection["id"], "title": collection["title"], "handle": collection["handle"], "automated": collection.get("ruleSet") is not None}, **products}

    async def list_collection_rule_conditions(self, _: dict[str, Any]) -> dict[str, Any]:
        query = """query CollectionRuleConditions{collectionRulesConditions{ruleType allowedRelations defaultRelation ruleObject{__typename}}}"""
        result = await self.client.graphql(query)
        conditions = result["data"]["collectionRulesConditions"]
        return {"conditions": conditions, "count": len(conditions)}

    async def prepare_collection_create(self, args: dict[str, Any]) -> dict[str, Any]:
        collection_input = _collection_input(args, include_id=False)
        warnings = _rule_set_warnings(collection_input.get("ruleSet"))
        if "ruleSet" in collection_input:
            warnings.insert(0, "A coleção será criada sem publicação; a membership vem da regra informada.")
        else:
            warnings.insert(0, "A coleção será criada sem publicação e sem fonte de produtos; configure membership e publicação separadamente.")
        token = self.confirmations.issue("shopify_create_collection", collection_input)
        return {"operation": "shopify_create_collection", "before": None, "after": collection_input, "warnings": warnings, **token}

    async def create_collection(self, args: dict[str, Any]) -> dict[str, Any]:
        collection_input = _collection_input(args, include_id=False)
        self._require_write(args, "shopify_create_collection", collection_input)
        query = """mutation CollectionCreate($collection:CollectionCreateInput!){collectionCreate(collection:$collection){collection{id title descriptionHtml handle sortOrder templateSuffix seo{title description} productsCount{count} updatedAt sources{__typename id title} ruleSet{appliedDisjunctively rules{column relation condition}}} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"collection": collection_input})
        return {"success": True, "operation": "collectionCreate", **mutation_result(result, "collectionCreate")}

    async def prepare_collection_update(self, args: dict[str, Any]) -> dict[str, Any]:
        changes = _collection_input(args, include_id=False)
        if not changes:
            raise ValueError("Informe ao menos um campo para alterar")
        warnings = _rule_set_warnings(changes.get("ruleSet"))
        result = await self.client.graphql("""query CollectionUpdatePreview($id:ID!){collection(id:$id){id title descriptionHtml handle sortOrder templateSuffix seo{title description} productsCount{count} sources{__typename id title} ruleSet{appliedDisjunctively rules{column relation condition}}}}""", {"id": args["id"]})
        collection = result["data"]["collection"]
        if collection is None:
            raise ShopifyError("Coleção não encontrada")
        before = {key: collection.get(key) for key in ("title", "descriptionHtml", "handle", "sortOrder", "templateSuffix", "seo", "ruleSet")}
        grouped = _grouped_condition_warning(before["ruleSet"]) if "ruleSet" in changes else None
        if grouped:
            warnings.insert(0, grouped)
        if "ruleSet" in changes and before["ruleSet"] is None:
            warnings.insert(0, "A coleção é manual hoje; ao receber uma regra ela vira automática e a seleção manual de produtos é descartada.")
        mutation_input = {"id": args["id"], **changes}
        token = self.confirmations.issue("shopify_update_collection", mutation_input)
        return {"collection": {"id": collection["id"], "title": collection["title"], "productsCount": collection.get("productsCount"), "sources": collection.get("sources")}, "before": before, "after": {**before, **changes}, "willChange": before_changed(before, {**before, **changes}), **({"warnings": warnings} if warnings else {}), **token}

    async def update_collection(self, args: dict[str, Any]) -> dict[str, Any]:
        collection_input = _collection_input(args, include_id=True)
        self._require_write(args, "shopify_update_collection", collection_input)
        query = """mutation CollectionUpdate($collection:CollectionUpdateInput!){collectionUpdate(collection:$collection){collection{id title descriptionHtml handle sortOrder templateSuffix seo{title description} productsCount{count} updatedAt sources{__typename id title} ruleSet{appliedDisjunctively rules{column relation condition}}} job{id done} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"collection": collection_input})
        return {"success": True, "operation": "collectionUpdate", **mutation_result(result, "collectionUpdate")}

    async def prepare_collection_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query CollectionDeletePreview($id:ID!){collection(id:$id){id title handle productsCount{count} publications(first:100){nodes{id name}}}}""", {"id": args["id"]})
        collection = result["data"]["collection"]
        if collection is None:
            raise ShopifyError("Coleção não encontrada")
        mutation_args = {"input": {"id": args["id"]}}
        token = self.confirmations.issue("shopify_delete_collection", mutation_args)
        return {"before": collection, "irreversible": True, "warnings": ["A coleção será removida permanentemente de todos os canais. Os produtos não serão apagados."], **token}

    async def delete_collection(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"input": {"id": args["id"]}}
        self._require_write(args, "shopify_delete_collection", mutation_args)
        query = """mutation CollectionDelete($input:CollectionDeleteInput!){collectionDelete(input:$input){deletedCollectionId userErrors{field message}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "collectionDelete", **mutation_result(result, "collectionDelete")}

    async def list_locations(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Locations($first:Int!,$after:String){locations(first:$first,after:$after,includeInactive:true){edges{cursor node{id name isActive fulfillsOnlineOrders address{address1 address2 city provinceCode zip countryCode}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after")})
        return _connection(result["data"], "locations")

    async def list_inventory_items(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query InventoryItems($first:Int!,$after:String,$query:String){inventoryItems(first:$first,after:$after,query:$query){edges{cursor node{id sku tracked requiresShipping duplicateSkuCount updatedAt variants(first:10){nodes{id title product{id title handle}}} inventoryLevels(first:100,includeInactive:true){nodes{id canDeactivate location{id name isActive} quantities(names:[\"available\",\"on_hand\",\"committed\",\"incoming\",\"reserved\"]){name quantity}}}}}pageInfo{hasNextPage endCursor}}}"""
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "inventoryItems")

    async def get_inventory_item(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query InventoryItem($id:ID!,$first:Int!,$after:String){inventoryItem(id:$id){id sku tracked requiresShipping duplicateSkuCount countryCodeOfOrigin provinceCodeOfOrigin harmonizedSystemCode unitCost{amount currencyCode} updatedAt variants(first:20){nodes{id title product{id title handle}}} inventoryLevels(first:$first,after:$after,includeInactive:true){edges{cursor node{id canDeactivate location{id name isActive} quantities(names:[\"available\",\"on_hand\",\"committed\",\"incoming\",\"reserved\"]){name quantity}}}pageInfo{hasNextPage endCursor}}}}"""
        result = await self.client.graphql(query, {"id": args["id"], "first": _page_size(args.get("first")), "after": args.get("after")})
        item = result["data"]["inventoryItem"]
        if item is None:
            return {"inventoryItem": None}
        levels = _connection(item, "inventoryLevels")
        return {"inventoryItem": {key: value for key, value in item.items() if key != "inventoryLevels"}, "levels": levels["items"], "pageInfo": levels["pageInfo"]}

    async def list_low_stock_variants(self, args: dict[str, Any]) -> dict[str, Any]:
        threshold = int(args.get("threshold", 5))
        filters = [f"inventory_quantity:<={threshold}"]
        if args.get("locationId"):
            filters.append(f"location_id:{args['locationId'].rsplit('/', 1)[-1]}")
        query = """query LowStock($first:Int!,$after:String,$query:String!){productVariants(first:$first,after:$after,query:$query,sortKey:INVENTORY_LEVELS_AVAILABLE){edges{cursor node{id title displayName sku barcode inventoryQuantity availableForSale product{id title handle status} inventoryItem{id tracked requiresShipping inventoryLevels(first:20){nodes{id location{id name isActive} quantities(names:[\"available\",\"on_hand\",\"committed\",\"reserved\",\"incoming\"]){name quantity}}}}}}}pageInfo{hasNextPage endCursor}}}"""
        variables = {"first": _page_size(args.get("first")), "after": args.get("after"), "query": " AND ".join(filters)}
        result = await self.client.graphql(query, variables)
        response = _connection(result["data"], "productVariants")
        return {**response, "threshold": threshold, "locationId": args.get("locationId"), "inventorySemantics": "inventoryQuantity is aggregate; inspect inventoryLevels for the selected locations"}

    async def prepare_inventory_adjust(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = [change["inventoryItemId"] for change in args["changes"]]
        if len({(change["inventoryItemId"], change["locationId"]) for change in args["changes"]}) != len(args["changes"]):
            raise ValueError("Cada par item/local pode aparecer apenas uma vez")
        result = await self.client.graphql("""query InventoryAdjustPreview($ids:[ID!]!){nodes(ids:$ids){... on InventoryItem{id sku tracked inventoryLevels(first:100,includeInactive:true){nodes{location{id name isActive} quantities(names:[\"available\"]){name quantity}}}}}}""", {"ids": ids})
        found = {node["id"]: node for node in result["data"]["nodes"] if node}
        missing = sorted(set(ids) - set(found))
        if missing:
            raise ShopifyError("Um ou mais itens de estoque não foram encontrados", details={"missingIds": missing})
        before = []
        for change in args["changes"]:
            item = found[change["inventoryItemId"]]
            if not item["tracked"]:
                raise ShopifyError("O item não possui rastreamento de estoque ativo", details={"inventoryItemId": item["id"]})
            level = next((level for level in item["inventoryLevels"]["nodes"] if level["location"]["id"] == change["locationId"]), None)
            if level is None:
                raise ShopifyError("O item não está ativo no local informado", details={"inventoryItemId": item["id"], "locationId": change["locationId"]})
            current = next(quantity["quantity"] for quantity in level["quantities"] if quantity["name"] == args["name"])
            if current != change["changeFromQuantity"]:
                raise ShopifyError("Quantidade informada está desatualizada", details={"inventoryItemId": item["id"], "locationId": change["locationId"], "expected": change["changeFromQuantity"], "current": current})
            before.append({"inventoryItemId": item["id"], "sku": item.get("sku"), "location": level["location"], "quantity": current, "after": current + change["delta"]})
        inventory_input = {key: args[key] for key in ("name", "reason", "referenceDocumentUri", "changes")}
        idempotency_key = str(uuid4())
        mutation_args = {"input": inventory_input, "idempotencyKey": idempotency_key}
        token = self.confirmations.issue("shopify_inventory_adjust", mutation_args)
        return {"beforeAfter": before, "atomic": True, "compareAndSwap": True, "idempotencyKey": idempotency_key, **token}

    async def inventory_adjust(self, args: dict[str, Any]) -> dict[str, Any]:
        inventory_input = {key: args[key] for key in ("name", "reason", "referenceDocumentUri", "changes")}
        mutation_args = {"input": inventory_input, "idempotencyKey": args["idempotencyKey"]}
        self._require_write(args, "shopify_inventory_adjust", mutation_args)
        query = """mutation InventoryAdjust($input:InventoryAdjustQuantitiesInput!,$idempotencyKey:String!){inventoryAdjustQuantities(input:$input) @idempotent(key:$idempotencyKey){inventoryAdjustmentGroup{createdAt reason referenceDocumentUri changes{name delta quantityAfterChange}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "inventoryAdjustQuantities", "idempotencyKey": args["idempotencyKey"], **mutation_result(result, "inventoryAdjustQuantities")}

    async def prepare_inventory_item_weight_update(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql(
            """query WeightPreview($id:ID!){inventoryItem(id:$id){id sku tracked measurement{weight{value unit}} variant{id displayName product{id title}}}}""",
            {"id": args["inventoryItemId"]},
        )
        item = result["data"]["inventoryItem"]
        if item is None:
            raise ShopifyError("Item de estoque não encontrado")
        before = (item.get("measurement") or {}).get("weight")
        after = {"value": args["weight"]["value"], "unit": args["weight"]["unit"]}
        variant = item.get("variant") or {}
        product = variant.get("product") or {}
        mutation_args = {"inventoryItemId": args["inventoryItemId"], "weight": after}
        token = self.confirmations.issue("shopify_inventory_item_weight_update", mutation_args)
        return {
            "inventoryItem": {"id": item["id"], "sku": item.get("sku")},
            "variant": {"id": variant.get("id"), "displayName": variant.get("displayName")},
            "product": {"id": product.get("id"), "title": product.get("title")},
            "before": before,
            "after": after,
            "willChange": before_changed(before, after),
            **token,
        }

    async def inventory_item_weight_update(self, args: dict[str, Any]) -> dict[str, Any]:
        weight = {"value": args["weight"]["value"], "unit": args["weight"]["unit"]}
        mutation_args = {"inventoryItemId": args["inventoryItemId"], "weight": weight}
        self._require_write(args, "shopify_inventory_item_weight_update", mutation_args)
        query = """mutation WeightUpdate($id:ID!,$input:InventoryItemInput!){inventoryItemUpdate(id:$id,input:$input){inventoryItem{id measurement{weight{value unit}}} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"id": args["inventoryItemId"], "input": {"measurement": {"weight": weight}}})
        return {"success": True, "operation": "inventoryItemUpdate", **mutation_result(result, "inventoryItemUpdate")}

    async def prepare_inventory_activation_toggle(self, args: dict[str, Any]) -> dict[str, Any]:
        location_ids = [update["locationId"] for update in args["updates"]]
        if len(set(location_ids)) != len(location_ids):
            raise ValueError("Cada local pode aparecer apenas uma vez")
        result = await self.client.graphql("""query InventoryActivationPreview($itemId:ID!,$locationIds:[ID!]!){inventoryItem(id:$itemId){id sku tracked inventoryLevels(first:100,includeInactive:true){nodes{location{id name isActive} quantities(names:[\"available\",\"on_hand\",\"committed\",\"incoming\",\"reserved\"]){name quantity}}}} nodes(ids:$locationIds){... on Location{id name isActive}}}""", {"itemId": args["inventoryItemId"], "locationIds": location_ids})
        item = result["data"]["inventoryItem"]
        if item is None:
            raise ShopifyError("Item de estoque não encontrado")
        locations = {node["id"]: node for node in result["data"]["nodes"] if node}
        missing = sorted(set(location_ids) - set(locations))
        if missing:
            raise ShopifyError("Um ou mais locais não foram encontrados", details={"missingIds": missing})
        levels = {level["location"]["id"]: level for level in item["inventoryLevels"]["nodes"]}
        changes = []
        warnings = []
        for update in args["updates"]:
            location_id = update["locationId"]
            currently_active = location_id in levels
            if update["activate"] and not locations[location_id]["isActive"]:
                raise ShopifyError("Não é possível ativar estoque em um local inativo", details={"locationId": location_id})
            entry = {"location": locations[location_id], "beforeActive": currently_active, "afterActive": update["activate"], "willChange": currently_active != update["activate"]}
            if currently_active:
                entry["currentQuantities"] = levels[location_id]["quantities"]
            changes.append(entry)
            if currently_active and not update["activate"]:
                warnings.append(f"Desativar {locations[location_id]['name']} remove todas as quantidades desse nível.")
        mutation_args = {"inventoryItemId": args["inventoryItemId"], "inventoryItemUpdates": args["updates"]}
        token = self.confirmations.issue("shopify_inventory_activation_toggle", mutation_args)
        return {"inventoryItem": {"id": item["id"], "sku": item.get("sku"), "tracked": item["tracked"]}, "changes": changes, "warnings": warnings, **token}

    async def inventory_activation_toggle(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"inventoryItemId": args["inventoryItemId"], "inventoryItemUpdates": args["updates"]}
        self._require_write(args, "shopify_inventory_activation_toggle", mutation_args)
        query = """mutation InventoryActivationToggle($inventoryItemId:ID!,$inventoryItemUpdates:[InventoryBulkToggleActivationInput!]!){inventoryBulkToggleActivation(inventoryItemId:$inventoryItemId,inventoryItemUpdates:$inventoryItemUpdates){inventoryItem{id sku tracked} inventoryLevels{id location{id name isActive} quantities(names:[\"available\",\"on_hand\"]){name quantity}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "inventoryBulkToggleActivation", **mutation_result(result, "inventoryBulkToggleActivation")}

    def _require_write(self, args: dict[str, Any], tool: str, mutation_args: dict[str, Any]) -> dict[str, Any] | None:
        if not self.client.settings.enable_writes:
            raise ShopifyError("Escritas desabilitadas. Configure SHOPIFY_ENABLE_WRITES=true e reinicie o servidor.")
        token = args.get("confirmationToken")
        if not isinstance(token, str):
            raise ShopifyError("Operação não executada: prepare a alteração e envie confirmationToken.")
        return self.confirmations.consume(token, tool, mutation_args)

    @staticmethod
    def _unique_metafields(items: list[dict[str, Any]]) -> None:
        identifiers = [(item["ownerId"], item["namespace"], item["key"]) for item in items]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("Cada combinação ownerId/namespace/key pode aparecer apenas uma vez")

    async def _fetch_metafields(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        declarations, selections, variables = [], [], {}
        for index, item in enumerate(items):
            declarations.extend([f"$owner{index}:ID!", f"$namespace{index}:String!", f"$key{index}:String!"])
            selections.append(f'''item{index}:node(id:$owner{index}){{id __typename ... on HasMetafields{{selected:metafield(namespace:$namespace{index},key:$key{index}){{id namespace key type value compareDigest createdAt updatedAt}}}}}}''')
            variables.update({f"owner{index}": item["ownerId"], f"namespace{index}": item["namespace"], f"key{index}": item["key"]})
        query = f"query MetafieldPreview({','.join(declarations)}){{{''.join(selections)}}}"
        result = await self.client.graphql(query, variables)
        return [result["data"][f"item{index}"] for index in range(len(items))]

    async def get_metafield(self, args: dict[str, Any]) -> dict[str, Any]:
        nodes = await self._fetch_metafields([args])
        owner = nodes[0]
        if owner is None:
            raise ShopifyError("Owner não encontrado")
        if "selected" not in owner:
            raise ShopifyError("O recurso informado não suporta metafields")
        return {"owner": {"id": owner["id"], "type": owner["__typename"]}, "metafield": owner.get("selected")}

    async def prepare_metafields_set(self, args: dict[str, Any]) -> dict[str, Any]:
        items = args["metafields"]
        self._unique_metafields(items)
        owners = await self._fetch_metafields(items)
        before = []
        for item, owner in zip(items, owners, strict=True):
            if owner is None:
                raise ShopifyError("Owner de metafield não encontrado", details={"ownerId": item["ownerId"]})
            if "selected" not in owner:
                raise ShopifyError("O recurso não suporta metafields", details={"ownerId": item["ownerId"]})
            current = owner.get("selected")
            expected = item["compareDigest"]
            if current is None and expected is not None:
                raise ShopifyError("Metafield inexistente: use compareDigest null para criação exclusiva")
            if current is not None and expected != current.get("compareDigest"):
                raise ShopifyError("compareDigest desatualizado; leia novamente antes de sobrescrever")
            if current is not None and item["type"] != current.get("type"):
                raise ShopifyError("O tipo de um metafield existente não pode ser alterado por esta operação")
            before.append({"owner": {"id": owner["id"], "type": owner["__typename"]}, "metafield": current})
        mutation_args = {"metafields": items}
        token = self.confirmations.issue("shopify_metafields_set", mutation_args)
        return {"before": before, "requested": items, "atomic": True, **token}

    async def metafields_set(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"metafields": args["metafields"]}
        self._require_write(args, "shopify_metafields_set", mutation_args)
        query = """mutation MetafieldsSet($metafields:[MetafieldsSetInput!]!){metafieldsSet(metafields:$metafields){metafields{id ownerType namespace key type value compareDigest createdAt updatedAt} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "metafieldsSet", "atomic": True, **mutation_result(result, "metafieldsSet")}

    async def prepare_metafields_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        items = args["metafields"]
        self._unique_metafields(items)
        owners = await self._fetch_metafields(items)
        current = []
        for item, owner in zip(items, owners, strict=True):
            metafield = owner.get("selected") if owner else None
            if metafield is None:
                raise ShopifyError("Metafield não encontrado para exclusão")
            if item["compareDigest"] != metafield.get("compareDigest"):
                raise ShopifyError("compareDigest desatualizado; leia novamente antes de excluir")
            current.append(metafield)
        mutation_args = {"metafields": items}
        token = self.confirmations.issue("shopify_metafields_delete", mutation_args)
        return {"before": current, "willDelete": len(items), "warnings": ["A exclusão é permanente e será revalidada antes da mutation."], **token}

    async def metafields_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"metafields": args["metafields"]}
        self._require_write(args, "shopify_metafields_delete", mutation_args)
        owners = await self._fetch_metafields(args["metafields"])
        for item, owner in zip(args["metafields"], owners, strict=True):
            current = owner.get("selected") if owner else None
            if current is None or current.get("compareDigest") != item["compareDigest"]:
                raise ShopifyError("Exclusão cancelada: o metafield mudou após a preparação")
        identifiers = [{key: item[key] for key in ("ownerId", "namespace", "key")} for item in args["metafields"]]
        query = """mutation MetafieldsDelete($metafields:[MetafieldIdentifierInput!]!){metafieldsDelete(metafields:$metafields){deletedMetafields{ownerId namespace key} userErrors{field message code}}}"""
        result = await self.client.graphql(query, {"metafields": identifiers})
        return {"success": True, "operation": "metafieldsDelete", **mutation_result(result, "metafieldsDelete")}

    _METAFIELD_DEFINITION_FIELDS = "id name namespace key description ownerType type{name category} pinnedPosition validations{name value} access{admin storefront customerAccount}"

    async def list_metafield_definitions(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"""query MetafieldDefinitions($ownerType:MetafieldOwnerType!,$first:Int!,$after:String,$query:String){{metafieldDefinitions(ownerType:$ownerType,first:$first,after:$after,query:$query){{edges{{cursor node{{{self._METAFIELD_DEFINITION_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"""
        result = await self.client.graphql(query, {"ownerType": args["ownerType"], "first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "metafieldDefinitions")

    async def get_metafield_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query MetafieldDefinition($id:ID!){{metafieldDefinition(id:$id){{{self._METAFIELD_DEFINITION_FIELDS}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"definition": result["data"]["metafieldDefinition"]}

    async def _definition_by_identifier(self, args: dict[str, Any]) -> dict[str, Any] | None:
        identifier = {key: args[key] for key in ("namespace", "key", "ownerType")}
        query = f"query MetafieldDefinitionByIdentifier($identifier:MetafieldDefinitionIdentifierInput!){{metafieldDefinition(identifier:$identifier){{{self._METAFIELD_DEFINITION_FIELDS}}}}}"
        result = await self.client.graphql(query, {"identifier": identifier})
        return result["data"]["metafieldDefinition"]

    @staticmethod
    def _definition_create_input(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("name", "namespace", "key", "description", "type", "ownerType", "pin", "validations") if key in args}

    @staticmethod
    def _definition_update_input(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("namespace", "key", "ownerType", "name", "description", "validations") if key in args}

    async def prepare_metafield_definition_create(self, args: dict[str, Any]) -> dict[str, Any]:
        if await self._definition_by_identifier(args) is not None:
            raise ShopifyError("Já existe uma definição com esse ownerType, namespace e key")
        definition = self._definition_create_input(args)
        token = self.confirmations.issue("shopify_create_metafield_definition", definition)
        return {"willCreate": definition, "warnings": ["Metafields existentes com o mesmo identificador serão validados pela Shopify contra o novo schema."], **token}

    async def create_metafield_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        definition = self._definition_create_input(args)
        self._require_write(args, "shopify_create_metafield_definition", definition)
        query = f"mutation MetafieldDefinitionCreate($definition:MetafieldDefinitionInput!){{metafieldDefinitionCreate(definition:$definition){{createdDefinition{{{self._METAFIELD_DEFINITION_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, {"definition": definition})
        return {"success": True, "operation": "metafieldDefinitionCreate", **mutation_result(result, "metafieldDefinitionCreate")}

    async def prepare_metafield_definition_update(self, args: dict[str, Any]) -> dict[str, Any]:
        changes = {key: args[key] for key in ("name", "description", "validations") if key in args}
        if not changes:
            raise ValueError("Informe name, description e/ou validations para alterar")
        current = await self._definition_by_identifier(args)
        if current is None:
            raise ShopifyError("Definição de metafield não encontrada")
        definition = self._definition_update_input(args)
        token = self.confirmations.issue("shopify_update_metafield_definition", definition)
        return {"before": current, "requestedChanges": changes, **token}

    async def update_metafield_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        definition = self._definition_update_input(args)
        self._require_write(args, "shopify_update_metafield_definition", definition)
        query = f"mutation MetafieldDefinitionUpdate($definition:MetafieldDefinitionUpdateInput!){{metafieldDefinitionUpdate(definition:$definition){{updatedDefinition{{{self._METAFIELD_DEFINITION_FIELDS}}} validationJob{{id done}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, {"definition": definition})
        return {"success": True, "operation": "metafieldDefinitionUpdate", **mutation_result(result, "metafieldDefinitionUpdate")}

    async def prepare_metafield_definition_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        definition = (await self.get_metafield_definition({"id": args["id"]}))["definition"]
        if definition is None:
            raise ShopifyError("Definição de metafield não encontrada")
        if definition["namespace"].startswith("$app") and not args["deleteAllAssociatedMetafields"]:
            raise ShopifyError("Definições $app exigem deleteAllAssociatedMetafields=true na Shopify")
        mutation_args = {key: args[key] for key in ("id", "deleteAllAssociatedMetafields")}
        token = self.confirmations.issue("shopify_delete_metafield_definition", mutation_args)
        warnings = ["A definição será excluída."]
        if args["deleteAllAssociatedMetafields"]:
            warnings.append("Todos os metafields associados serão excluídos assincronamente e de forma permanente.")
        return {"definition": definition, "warnings": warnings, **token}

    async def delete_metafield_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {key: args[key] for key in ("id", "deleteAllAssociatedMetafields")}
        self._require_write(args, "shopify_delete_metafield_definition", mutation_args)
        query = """mutation MetafieldDefinitionDelete($id:ID!,$deleteAllAssociatedMetafields:Boolean!){metafieldDefinitionDelete(id:$id,deleteAllAssociatedMetafields:$deleteAllAssociatedMetafields){deletedDefinitionId deletedDefinition{namespace key ownerType} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "metafieldDefinitionDelete", **mutation_result(result, "metafieldDefinitionDelete")}

    _METAOBJECT_DEFINITION_FIELDS = "id name type description displayNameKey metaobjectsCount fieldDefinitions{key name description required type{name category} validations{name value}} access{admin storefront customerAccount} capabilities{publishable{enabled} translatable{enabled} renderable{enabled} onlineStore{enabled}} createdAt updatedAt"
    _METAOBJECT_FIELDS = "id type handle displayName fields{key value type} capabilities{publishable{status}} definition{id name type displayNameKey} createdAt updatedAt"

    async def list_metaobject_definitions(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query MetaobjectDefinitions($first:Int!,$after:String){{metaobjectDefinitions(first:$first,after:$after){{edges{{cursor node{{{self._METAOBJECT_DEFINITION_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after")})
        return _connection(result["data"], "metaobjectDefinitions")

    async def get_metaobject_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query MetaobjectDefinition($id:ID!){{metaobjectDefinition(id:$id){{{self._METAOBJECT_DEFINITION_FIELDS}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"definition": result["data"]["metaobjectDefinition"]}

    async def get_metaobject_definition_by_type(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query MetaobjectDefinitionByType($type:String!){{metaobjectDefinitionByType(type:$type){{{self._METAOBJECT_DEFINITION_FIELDS}}}}}"
        result = await self.client.graphql(query, {"type": args["type"]})
        return {"definition": result["data"]["metaobjectDefinitionByType"]}

    @staticmethod
    def _validate_metaobject_definition(args: dict[str, Any]) -> None:
        fields = args["fieldDefinitions"]
        keys = [field["key"] for field in fields]
        if len(set(keys)) != len(keys):
            raise ValueError("Cada key de fieldDefinitions deve ser única")
        if args.get("displayNameKey") and args["displayNameKey"] not in keys:
            raise ValueError("displayNameKey deve apontar para uma fieldDefinition informada")

    async def prepare_metaobject_definition_create(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_metaobject_definition(args)
        existing = (await self.get_metaobject_definition_by_type({"type": args["type"]}))["definition"]
        if existing is not None:
            raise ShopifyError("Já existe uma definição com esse type")
        definition = {key: args[key] for key in ("name", "type", "description", "displayNameKey", "access", "fieldDefinitions") if key in args}
        token = self.confirmations.issue("shopify_create_metaobject_definition", definition)
        return {"willCreate": definition, "fieldCount": len(args["fieldDefinitions"]), **token}

    async def create_metaobject_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        definition = {key: args[key] for key in ("name", "type", "description", "displayNameKey", "access", "fieldDefinitions") if key in args}
        self._require_write(args, "shopify_create_metaobject_definition", definition)
        query = f"mutation MetaobjectDefinitionCreate($definition:MetaobjectDefinitionCreateInput!){{metaobjectDefinitionCreate(definition:$definition){{metaobjectDefinition{{{self._METAOBJECT_DEFINITION_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, {"definition": definition})
        return {"success": True, "operation": "metaobjectDefinitionCreate", **mutation_result(result, "metaobjectDefinitionCreate")}

    @staticmethod
    def _metaobject_definition_update_input(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("name", "description", "displayNameKey", "access", "fieldDefinitions", "resetFieldOrder") if key in args}

    @staticmethod
    def _validate_metaobject_field_operations(current: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        fields = {field["key"]: dict(field) for field in current["fieldDefinitions"]}
        seen: set[str] = set()
        destructive = []
        for operation in args.get("fieldDefinitions", []):
            action = next(iter(operation))
            payload = operation[action]
            key = payload["key"]
            if key in seen:
                raise ValueError("Cada field key pode participar de apenas uma operação")
            seen.add(key)
            if action == "create":
                if key in fields:
                    raise ShopifyError("Não é possível criar uma field key já existente", details={"key": key})
                fields[key] = payload
            elif action == "update":
                if key not in fields:
                    raise ShopifyError("Field key não encontrada para update", details={"key": key})
                fields[key].update({k: v for k, v in payload.items() if k != "key"})
                if payload.get("required") is True and not current_field_required(current, key):
                    destructive.append({"key": key, "impact": "existing entries without a value can fail validation"})
            else:
                if key not in fields:
                    raise ShopifyError("Field key não encontrada para delete", details={"key": key})
                destructive.append({"key": key, "impact": "values are removed from every metaobject entry"})
                del fields[key]
        display_name = args.get("displayNameKey", current.get("displayNameKey"))
        if display_name is not None and display_name not in fields:
            raise ValueError("O displayNameKey final deve apontar para uma field existente")
        if destructive and not args["acknowledgeFieldDataLoss"]:
            raise ShopifyError("Alteração estrutural exige acknowledgeFieldDataLoss=true", details={"impacts": destructive})
        return {"finalFieldKeys": list(fields), "destructiveImpacts": destructive}

    async def prepare_metaobject_definition_update(self, args: dict[str, Any]) -> dict[str, Any]:
        current = (await self.get_metaobject_definition({"id": args["id"]}))["definition"]
        if current is None:
            raise ShopifyError("Definição de metaobject não encontrada")
        definition = self._metaobject_definition_update_input(args)
        if not definition:
            raise ValueError("Informe ao menos uma alteração para a definição")
        validation = self._validate_metaobject_field_operations(current, args)
        mutation_args = {"id": args["id"], "definition": definition, "acknowledgeFieldDataLoss": args["acknowledgeFieldDataLoss"]}
        token = self.confirmations.issue("shopify_update_metaobject_definition", mutation_args)
        return {"before": current, "requestedChanges": definition, **validation, **token}

    async def update_metaobject_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        definition = self._metaobject_definition_update_input(args)
        mutation_args = {"id": args["id"], "definition": definition, "acknowledgeFieldDataLoss": args["acknowledgeFieldDataLoss"]}
        self._require_write(args, "shopify_update_metaobject_definition", mutation_args)
        query = f"mutation MetaobjectDefinitionUpdate($id:ID!,$definition:MetaobjectDefinitionUpdateInput!){{metaobjectDefinitionUpdate(id:$id,definition:$definition){{metaobjectDefinition{{{self._METAOBJECT_DEFINITION_FIELDS}}} userErrors{{field message code elementIndex elementKey}}}}}}"
        result = await self.client.graphql(query, {"id": args["id"], "definition": definition})
        return {"success": True, "operation": "metaobjectDefinitionUpdate", **mutation_result(result, "metaobjectDefinitionUpdate")}

    async def prepare_metaobject_definition_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        if args["confirmCascade"] is not True:
            raise ShopifyError("confirmCascade=true é obrigatório: a Shopify apaga todo o grafo relacionado")
        definition = (await self.get_metaobject_definition({"id": args["id"]}))["definition"]
        if definition is None:
            raise ShopifyError("Definição de metaobject não encontrada")
        mutation_args = {"id": args["id"], "confirmCascade": True}
        token = self.confirmations.issue("shopify_delete_metaobject_definition", mutation_args)
        return {"definition": definition, "cascade": {"metaobjects": definition.get("metaobjectsCount"), "alsoDeletes": ["metaobject instances", "related metafield definitions", "related metafields"]}, "warnings": ["A exclusão ocorre assincronamente e é permanente."], **token}

    async def delete_metaobject_definition(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "confirmCascade": args["confirmCascade"]}
        self._require_write(args, "shopify_delete_metaobject_definition", mutation_args)
        query = "mutation MetaobjectDefinitionDelete($id:ID!){metaobjectDefinitionDelete(id:$id){deletedId userErrors{field message code}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"success": True, "operation": "metaobjectDefinitionDelete", **mutation_result(result, "metaobjectDefinitionDelete")}

    async def list_metaobjects(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Metaobjects($type:String!,$first:Int!,$after:String,$query:String){{metaobjects(type:$type,first:$first,after:$after,query:$query){{edges{{cursor node{{{self._METAOBJECT_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"type": args["type"], "first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "metaobjects")

    async def get_metaobject(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Metaobject($id:ID!){{metaobject(id:$id){{{self._METAOBJECT_FIELDS}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"metaobject": result["data"]["metaobject"]}

    async def get_metaobject_by_handle(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query MetaobjectByHandle($handle:MetaobjectHandleInput!){{metaobjectByHandle(handle:$handle){{{self._METAOBJECT_FIELDS}}}}}"
        result = await self.client.graphql(query, {"handle": {"type": args["type"], "handle": args["handle"]}})
        return {"metaobject": result["data"]["metaobjectByHandle"]}

    @staticmethod
    def _metaobject_input(args: dict[str, Any], *, include_type: bool) -> dict[str, Any]:
        keys = ("type", "handle", "fields", "capabilities") if include_type else ("handle", "fields", "capabilities", "redirectNewHandle")
        return {key: args[key] for key in keys if key in args}

    @staticmethod
    def _validate_metaobject_fields(definition: dict[str, Any], fields: list[dict[str, Any]], *, creating: bool) -> None:
        keys = [item["key"] for item in fields]
        if len(set(keys)) != len(keys):
            raise ValueError("Cada key pode aparecer apenas uma vez em fields")
        allowed = {item["key"]: item for item in definition["fieldDefinitions"]}
        unknown = sorted(set(keys) - set(allowed))
        if unknown:
            raise ShopifyError("Campos não definidos no schema", details={"keys": unknown})
        if creating:
            supplied = {item["key"] for item in fields if item["value"] is not None}
            missing = sorted(key for key, item in allowed.items() if item["required"] and key not in supplied)
            if missing:
                raise ShopifyError("Campos obrigatórios ausentes", details={"keys": missing})

    async def prepare_metaobject_create(self, args: dict[str, Any]) -> dict[str, Any]:
        definition = (await self.get_metaobject_definition_by_type({"type": args["type"]}))["definition"]
        if definition is None:
            raise ShopifyError("Definição de metaobject não encontrada")
        self._validate_metaobject_fields(definition, args["fields"], creating=True)
        if args.get("handle"):
            existing = (await self.get_metaobject_by_handle({"type": args["type"], "handle": args["handle"]}))["metaobject"]
            if existing is not None:
                raise ShopifyError("Já existe um metaobject com esse type e handle")
        metaobject = self._metaobject_input(args, include_type=True)
        token = self.confirmations.issue("shopify_create_metaobject", metaobject)
        return {"definition": definition, "willCreate": metaobject, **token}

    async def create_metaobject(self, args: dict[str, Any]) -> dict[str, Any]:
        metaobject = self._metaobject_input(args, include_type=True)
        self._require_write(args, "shopify_create_metaobject", metaobject)
        query = f"mutation MetaobjectCreate($metaobject:MetaobjectCreateInput!){{metaobjectCreate(metaobject:$metaobject){{metaobject{{{self._METAOBJECT_FIELDS}}} userErrors{{field message code elementIndex elementKey}}}}}}"
        result = await self.client.graphql(query, {"metaobject": metaobject})
        return {"success": True, "operation": "metaobjectCreate", **mutation_result(result, "metaobjectCreate")}

    async def prepare_metaobject_update(self, args: dict[str, Any]) -> dict[str, Any]:
        metaobject = (await self.get_metaobject({"id": args["id"]}))["metaobject"]
        if metaobject is None:
            raise ShopifyError("Metaobject não encontrado")
        changes = self._metaobject_input(args, include_type=False)
        if not changes:
            raise ValueError("Informe fields, handle e/ou capabilities para alterar")
        if args.get("redirectNewHandle") and "handle" not in args:
            raise ValueError("redirectNewHandle exige um novo handle")
        if "fields" in args:
            definition = (await self.get_metaobject_definition_by_type({"type": metaobject["type"]}))["definition"]
            self._validate_metaobject_fields(definition, args["fields"], creating=False)
        mutation_args = {"id": args["id"], "metaobject": changes}
        token = self.confirmations.issue("shopify_update_metaobject", mutation_args)
        return {"before": metaobject, "requestedChanges": changes, **token}

    async def update_metaobject(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "metaobject": self._metaobject_input(args, include_type=False)}
        self._require_write(args, "shopify_update_metaobject", mutation_args)
        query = f"mutation MetaobjectUpdate($id:ID!,$metaobject:MetaobjectUpdateInput!){{metaobjectUpdate(id:$id,metaobject:$metaobject){{metaobject{{{self._METAOBJECT_FIELDS}}} userErrors{{field message code elementIndex elementKey}}}}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "metaobjectUpdate", **mutation_result(result, "metaobjectUpdate")}

    async def prepare_metaobject_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        metaobject = (await self.get_metaobject(args))["metaobject"]
        if metaobject is None:
            raise ShopifyError("Metaobject não encontrado")
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_delete_metaobject", mutation_args)
        return {"metaobject": metaobject, "warnings": ["A instância e seus metafields serão excluídos permanentemente; referências podem ficar sem destino."], **token}

    async def delete_metaobject(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_delete_metaobject", mutation_args)
        query = "mutation MetaobjectDelete($id:ID!){metaobjectDelete(id:$id){deletedId userErrors{field message code}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "metaobjectDelete", **mutation_result(result, "metaobjectDelete")}

    _FILE_FIELDS = """__typename id alt createdAt updatedAt fileStatus fileErrors{code message details} ... on GenericFile{url mimeType originalFileSize} ... on MediaImage{mimeType status image{id url width height altText} originalSource{url width height}} ... on Video{status duration preview{status image{id url width height}} originalSource{url width height format mimeType} sources{url width height format mimeType}} ... on ExternalVideo{status host originUrl embeddedUrl} ... on Model3d{status originalSource{url filesize}}"""

    async def list_files(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Files($first:Int!,$after:String,$query:String){{files(first:$first,after:$after,query:$query){{edges{{cursor node{{{self._FILE_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "files")

    async def get_file(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query File($id:ID!){{node(id:$id){{... on File{{{self._FILE_FIELDS}}}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"file": result["data"]["node"]}

    async def _files_by_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        query = f"query FilesByIds($ids:[ID!]!){{nodes(ids:$ids){{... on File{{{self._FILE_FIELDS}}}}}}}"
        result = await self.client.graphql(query, {"ids": ids})
        nodes = result["data"]["nodes"]
        missing = [file_id for file_id, node in zip(ids, nodes, strict=True) if node is None]
        if missing:
            raise ShopifyError("Um ou mais arquivos não foram encontrados", details={"missingIds": missing})
        return nodes

    async def prepare_files_create(self, args: dict[str, Any]) -> dict[str, Any]:
        files = args["files"]
        identities = [(item.get("filename"), item["originalSource"]) for item in files]
        if len(set(identities)) != len(identities):
            raise ValueError("O mesmo filename/originalSource não pode aparecer duas vezes no lote")
        replacement_count = sum(item["duplicateResolutionMode"] == "REPLACE" for item in files)
        mutation_args = {"files": files}
        token = self.confirmations.issue("shopify_files_create", mutation_args)
        warnings = ["A Shopify processa arquivos assincronamente; consulte fileStatus e fileErrors após a criação."]
        if replacement_count:
            warnings.append(f"{replacement_count} item(ns) usam REPLACE e podem substituir arquivos de mesmo nome.")
        return {"willCreate": len(files), "files": files, "replacementCount": replacement_count, "warnings": warnings, **token}

    async def files_create(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"files": args["files"]}
        self._require_write(args, "shopify_files_create", mutation_args)
        query = f"mutation FilesCreate($files:[FileCreateInput!]!){{fileCreate(files:$files){{files{{{self._FILE_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "fileCreate", "processingIsAsync": True, **mutation_result(result, "fileCreate")}

    async def prepare_files_update(self, args: dict[str, Any]) -> dict[str, Any]:
        files = args["files"]
        ids = [item["id"] for item in files]
        if len(set(ids)) != len(ids):
            raise ValueError("Cada arquivo pode aparecer apenas uma vez no lote")
        for item in files:
            if len(item) == 1:
                raise ValueError("Cada arquivo deve informar ao menos uma alteração")
            added, removed = set(item.get("referencesToAdd", [])), set(item.get("referencesToRemove", []))
            if added & removed:
                raise ValueError("Um produto não pode ser adicionado e removido no mesmo update")
        current = await self._files_by_ids(ids)
        product_ids = sorted({product_id for item in files for key in ("referencesToAdd", "referencesToRemove") for product_id in item.get(key, [])})
        if product_ids:
            result = await self.client.graphql("query FileProducts($ids:[ID!]!){nodes(ids:$ids){... on Product{id title}}}", {"ids": product_ids})
            missing = [product_id for product_id, node in zip(product_ids, result["data"]["nodes"], strict=True) if node is None]
            if missing:
                raise ShopifyError("Produtos de referência não encontrados", details={"missingIds": missing})
        mutation_args = {"files": files}
        token = self.confirmations.issue("shopify_files_update", mutation_args)
        warnings = ["Substituir originalSource mantém a URL do arquivo, mas reinicia o processamento."] if any("originalSource" in item for item in files) else []
        if any(item.get("referencesToRemove") for item in files):
            warnings.append("Remover referência tira a mídia da galeria do produto e pode limpar imagens de variantes.")
        return {"before": current, "requestedChanges": files, "warnings": warnings, **token}

    async def files_update(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"files": args["files"]}
        self._require_write(args, "shopify_files_update", mutation_args)
        query = f"mutation FilesUpdate($files:[FileUpdateInput!]!){{fileUpdate(files:$files){{files{{{self._FILE_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "fileUpdate", "processingMayBeAsync": True, **mutation_result(result, "fileUpdate")}

    async def prepare_files_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        if args["confirmRemoveReferences"] is not True:
            raise ShopifyError("confirmRemoveReferences=true é obrigatório para excluir arquivos")
        files = await self._files_by_ids(args["fileIds"])
        mutation_args = {"fileIds": args["fileIds"], "confirmRemoveReferences": True}
        token = self.confirmations.issue("shopify_files_delete", mutation_args)
        return {"files": files, "willDelete": len(files), "warnings": ["A exclusão remove os arquivos da biblioteca e referências/associações em produtos."], **token}

    async def files_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"fileIds": args["fileIds"], "confirmRemoveReferences": args["confirmRemoveReferences"]}
        self._require_write(args, "shopify_files_delete", mutation_args)
        query = "mutation FilesDelete($fileIds:[ID!]!){fileDelete(fileIds:$fileIds){deletedFileIds userErrors{field message code}}}"
        result = await self.client.graphql(query, {"fileIds": args["fileIds"]})
        return {"success": True, "operation": "fileDelete", **mutation_result(result, "fileDelete")}

    async def prepare_staged_uploads_create(self, args: dict[str, Any]) -> dict[str, Any]:
        inputs = args["input"]
        filenames = [item["filename"] for item in inputs]
        if len(set(filenames)) != len(filenames):
            raise ValueError("Cada filename deve ser único no lote de staged uploads")
        missing_size = [item["filename"] for item in inputs if item["resource"] in {"VIDEO", "MODEL_3D"} and "fileSize" not in item]
        if missing_size:
            raise ValueError("fileSize é obrigatório para VIDEO e MODEL_3D")
        mutation_args = {"input": inputs}
        token = self.confirmations.issue("shopify_staged_uploads_create", mutation_args)
        return {"targetsRequested": len(inputs), "input": inputs, "nextSteps": ["Enviar os bytes diretamente ao url retornado usando httpMethod e parameters.", "Usar resourceUrl como originalSource em shopify_prepare_files_create."], "security": "O MCP não acessa caminhos locais nem transporta o conteúdo do arquivo.", **token}

    async def staged_uploads_create(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"input": args["input"]}
        self._require_write(args, "shopify_staged_uploads_create", mutation_args)
        query = "mutation StagedUploadsCreate($input:[StagedUploadInput!]!){stagedUploadsCreate(input:$input){stagedTargets{url resourceUrl parameters{name value}} userErrors{field message}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "stagedUploadsCreate", "containsTemporaryCredentials": True, **mutation_result(result, "stagedUploadsCreate")}

    async def _publication_preview(self, resource_id: str, publication_ids: list[str]) -> dict[str, Any]:
        declarations = ["$id:ID!", "$publicationIds:[ID!]!"] + [f"$publication{index}:ID!" for index in range(len(publication_ids))]
        status_fields = " ".join(f"publication{index}:publishedOnPublication(publicationId:$publication{index})" for index in range(len(publication_ids)))
        variables = {"id": resource_id, "publicationIds": publication_ids, **{f"publication{index}": value for index, value in enumerate(publication_ids)}}
        query = f"query PublicationPreview({','.join(declarations)}){{node(id:$id){{id __typename ... on Product{{title status requiresSellingPlan}} ... on Collection{{title handle}} ... on Publishable{{{status_fields}}}}} nodes(ids:$publicationIds){{... on Publication{{id name supportsFuturePublishing autoPublish}}}}}}"
        result = await self.client.graphql(query, variables)
        resource = result["data"]["node"]
        if resource is None or resource.get("__typename") not in {"Product", "Collection"}:
            raise ShopifyError("Produto ou coleção não encontrado")
        publication_nodes = result["data"]["nodes"]
        publications = {node["id"]: node for node in publication_nodes if node}
        missing = sorted(set(publication_ids) - set(publications))
        if missing:
            raise ShopifyError("Uma ou mais publicações não foram encontradas", details={"missingIds": missing})
        states = [{"publication": publications[publication_id], "published": resource.get(f"publication{index}", False)} for index, publication_id in enumerate(publication_ids)]
        return {"resource": resource, "states": states}

    async def get_publication_status(self, args: dict[str, Any]) -> dict[str, Any]:
        return await self._publication_preview(args["id"], args["publicationIds"])

    async def prepare_publish(self, args: dict[str, Any]) -> dict[str, Any]:
        publications = args["publications"]
        ids = [item["publicationId"] for item in publications]
        if len(set(ids)) != len(ids):
            raise ValueError("Cada publicação pode aparecer apenas uma vez")
        preview = await self._publication_preview(args["id"], ids)
        by_id = {item["publication"]["id"]: item for item in preview["states"]}
        for item in publications:
            if "publishDate" in item:
                if not by_id[item["publicationId"]]["publication"]["supportsFuturePublishing"]:
                    raise ShopifyError("O canal informado não suporta publicação futura", details={"publicationId": item["publicationId"]})
                when = datetime.fromisoformat(item["publishDate"].replace("Z", "+00:00"))
                if when <= datetime.now(when.tzinfo):
                    raise ValueError("publishDate deve estar no futuro")
        if preview["resource"]["__typename"] == "Product" and preview["resource"].get("status") != "ACTIVE":
            warning = "O produto só ficará visível quando seu status for ACTIVE."
        else:
            warning = None
        mutation_args = {"id": args["id"], "input": publications}
        token = self.confirmations.issue("shopify_publish", mutation_args)
        return {**preview, "requested": publications, "warnings": [warning] if warning else [], **token}

    async def publish(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "input": args["publications"]}
        self._require_write(args, "shopify_publish", mutation_args)
        query = """mutation Publish($id:ID!,$input:[PublicationInput!]!){publishablePublish(id:$id,input:$input){publishable{availablePublicationsCount{count} resourcePublicationsCount{count}} userErrors{field message}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "publishablePublish", **mutation_result(result, "publishablePublish")}

    async def prepare_unpublish(self, args: dict[str, Any]) -> dict[str, Any]:
        preview = await self._publication_preview(args["id"], args["publicationIds"])
        inputs = [{"publicationId": publication_id} for publication_id in args["publicationIds"]]
        mutation_args = {"id": args["id"], "input": inputs}
        token = self.confirmations.issue("shopify_unpublish", mutation_args)
        return {**preview, "willUnpublish": [state["publication"] for state in preview["states"] if state["published"]], "warnings": ["O recurso deixará de estar disponível nos canais selecionados."], **token}

    async def unpublish(self, args: dict[str, Any]) -> dict[str, Any]:
        inputs = [{"publicationId": publication_id} for publication_id in args["publicationIds"]]
        mutation_args = {"id": args["id"], "input": inputs}
        self._require_write(args, "shopify_unpublish", mutation_args)
        query = """mutation Unpublish($id:ID!,$input:[PublicationInput!]!){publishableUnpublish(id:$id,input:$input){publishable{availablePublicationsCount{count} resourcePublicationsCount{count}} userErrors{field message}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "publishableUnpublish", **mutation_result(result, "publishableUnpublish")}

    _MARKET_FIELDS = """id name handle status type currencySettings{baseCurrency{currencyCode} localCurrencies} regions(first:100){nodes{id name ... on MarketRegionCountry{code}} pageInfo{hasNextPage endCursor}} catalogs(first:100){nodes{id title} pageInfo{hasNextPage endCursor}} webPresences(first:20){nodes{id subfolderSuffix domain{id host url}} pageInfo{hasNextPage endCursor}} catalogsCount{count}"""

    async def list_markets(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Markets($first:Int!,$after:String,$query:String){{markets(first:$first,after:$after,query:$query){{edges{{cursor node{{{self._MARKET_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "markets")

    async def get_market(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Market($id:ID!){{market(id:$id){{{self._MARKET_FIELDS}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"market": result["data"]["market"]}

    @staticmethod
    def _validate_market_input(args: dict[str, Any]) -> None:
        conditions = args.get("conditions")
        if conditions:
            codes = [item["countryCode"] for item in conditions["regionsCondition"]["regions"]]
            if len(set(codes)) != len(codes):
                raise ValueError("Cada countryCode pode aparecer apenas uma vez")
        if args.get("removeCurrencySettings") and "currencySettings" in args:
            raise ValueError("removeCurrencySettings não pode ser combinado com currencySettings")
        added, deleted = set(args.get("catalogsToAdd", [])), set(args.get("catalogsToDelete", []))
        if added & deleted:
            raise ValueError("Um catálogo não pode ser adicionado e removido no mesmo update")

    @staticmethod
    def _market_create_input(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("name", "handle", "status", "conditions", "currencySettings", "catalogs", "makeDuplicateUniqueMarketsDraft") if key in args}

    @staticmethod
    def _market_update_input(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("name", "handle", "status", "conditions", "currencySettings", "removeCurrencySettings", "catalogsToAdd", "catalogsToDelete", "makeDuplicateUniqueMarketsDraft") if key in args}

    async def _validate_catalog_ids(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        result = await self.client.graphql("query MarketCatalogs($ids:[ID!]!){nodes(ids:$ids){... on Catalog{id title}}}", {"ids": ids})
        nodes = result["data"]["nodes"]
        missing = [catalog_id for catalog_id, node in zip(ids, nodes, strict=True) if node is None]
        if missing:
            raise ShopifyError("Um ou mais catálogos não foram encontrados", details={"missingIds": missing})
        return nodes

    async def prepare_market_create(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_market_input(args)
        if args.get("handle"):
            result = await self.client.graphql("query MarketHandle($query:String!){markets(first:2,query:$query){nodes{id name handle status}}}", {"query": _search_exact("handle", args["handle"])})
            if result["data"]["markets"]["nodes"]:
                raise ShopifyError("Já existe um mercado com esse handle")
        catalogs = await self._validate_catalog_ids(args.get("catalogs", []))
        market_input = self._market_create_input(args)
        token = self.confirmations.issue("shopify_market_create", market_input)
        warnings = []
        if args["status"] == "ACTIVE":
            warnings.append("O mercado será ativado imediatamente para compradores que correspondam às condições.")
        if args["makeDuplicateUniqueMarketsDraft"]:
            warnings.append("Mercados exclusivos conflitantes poderão ser movidos automaticamente para DRAFT.")
        return {"willCreate": market_input, "validatedCatalogs": catalogs, "warnings": warnings, **token}

    async def market_create(self, args: dict[str, Any]) -> dict[str, Any]:
        market_input = self._market_create_input(args)
        self._require_write(args, "shopify_market_create", market_input)
        query = f"mutation MarketCreate($input:MarketCreateInput!){{marketCreate(input:$input){{market{{{self._MARKET_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, {"input": market_input})
        return {"success": True, "operation": "marketCreate", **mutation_result(result, "marketCreate")}

    async def prepare_market_update(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_market_input(args)
        current = (await self.get_market({"id": args["id"]}))["market"]
        if current is None:
            raise ShopifyError("Mercado não encontrado")
        market_input = self._market_update_input(args)
        if not market_input:
            raise ValueError("Informe ao menos uma alteração para o mercado")
        catalogs = await self._validate_catalog_ids(sorted(set(args.get("catalogsToAdd", []) + args.get("catalogsToDelete", []))))
        mutation_args = {"id": args["id"], "input": market_input}
        token = self.confirmations.issue("shopify_market_update", mutation_args)
        warnings = ["Alterar status para ACTIVE ou condições muda imediatamente quais compradores entram no mercado."] if args.get("status") == "ACTIVE" or "conditions" in args else []
        return {"before": current, "requestedChanges": market_input, "validatedCatalogs": catalogs, "warnings": warnings, **token}

    async def market_update(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "input": self._market_update_input(args)}
        self._require_write(args, "shopify_market_update", mutation_args)
        query = f"mutation MarketUpdate($id:ID!,$input:MarketUpdateInput!){{marketUpdate(id:$id,input:$input){{market{{{self._MARKET_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "marketUpdate", **mutation_result(result, "marketUpdate")}

    async def prepare_market_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        if args["confirmAssignmentsRemoval"] is not True:
            raise ShopifyError("confirmAssignmentsRemoval=true é obrigatório para excluir o mercado")
        market = (await self.get_market({"id": args["id"]}))["market"]
        if market is None:
            raise ShopifyError("Mercado não encontrado")
        mutation_args = {"id": args["id"], "confirmAssignmentsRemoval": True}
        token = self.confirmations.issue("shopify_market_delete", mutation_args)
        return {"market": market, "impact": {"regions": (market.get("regions") or {}).get("nodes", []), "catalogs": (market.get("catalogs") or {}).get("nodes", []), "webPresences": (market.get("webPresences") or {}).get("nodes", [])}, "warnings": ["A definição do mercado será excluída permanentemente e suas atribuições deixarão de valer."], **token}

    async def market_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "confirmAssignmentsRemoval": args["confirmAssignmentsRemoval"]}
        self._require_write(args, "shopify_market_delete", mutation_args)
        result = await self.client.graphql("mutation MarketDelete($id:ID!){marketDelete(id:$id){deletedId userErrors{field message code}}}", {"id": args["id"]})
        return {"success": True, "operation": "marketDelete", **mutation_result(result, "marketDelete")}

    _CATALOG_FIELDS = """__typename id title status publication{id name autoPublish} priceList{id name currency fixedPricesCount parent{adjustment{type value}}} ... on MarketCatalog{markets(first:20){nodes{id name handle status}}} ... on CompanyLocationCatalog{companyLocations(first:20){nodes{id name}}}"""
    _PRICE_LIST_FIELDS = """id name currency fixedPricesCount catalog{id title} parent{adjustment{type value}}"""

    async def list_catalogs(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Catalogs($first:Int!,$after:String,$query:String){{catalogs(first:$first,after:$after,query:$query){{edges{{cursor node{{{self._CATALOG_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "catalogs")

    async def get_catalog(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Catalog($id:ID!){{catalog(id:$id){{{self._CATALOG_FIELDS}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"catalog": result["data"]["catalog"]}

    async def list_price_lists(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query PriceLists($first:Int!,$after:String,$query:String){{priceLists(first:$first,after:$after,query:$query){{edges{{cursor node{{{self._PRICE_LIST_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "priceLists")

    async def get_price_list(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query PriceList($id:ID!,$first:Int!,$after:String,$query:String){{priceList(id:$id){{{self._PRICE_LIST_FIELDS} prices(first:$first,after:$after,query:$query){{nodes{{price{{amount currencyCode}} compareAtPrice{{amount currencyCode}} originType variant{{id title sku:inventoryItem{{sku}} product{{id title}}}}}} pageInfo{{hasNextPage endCursor}}}}}}}}"
        result = await self.client.graphql(query, {"id": args["id"], "first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return {"priceList": result["data"]["priceList"]}

    async def _fixed_prices_preview(self, price_list_id: str, variant_ids: list[str]) -> dict[str, Any]:
        declarations = ["$id:ID!", "$variantIds:[ID!]!"] + [f"$query{index}:String!" for index in range(len(variant_ids))]
        aliases = " ".join(f"price{index}:prices(first:1,query:$query{index}){{nodes{{price{{amount currencyCode}} compareAtPrice{{amount currencyCode}} originType variant{{id}}}}}}" for index in range(len(variant_ids)))
        variables = {"id": price_list_id, "variantIds": variant_ids, **{f"query{index}": _search_exact("variant_id", variant_id.rsplit('/', 1)[-1]) for index, variant_id in enumerate(variant_ids)}}
        query = f"query FixedPricesPreview({','.join(declarations)}){{priceList(id:$id){{{self._PRICE_LIST_FIELDS} {aliases}}} nodes(ids:$variantIds){{... on ProductVariant{{id title product{{id title}} inventoryItem{{sku}}}}}}}}"
        result = await self.client.graphql(query, variables)
        price_list = result["data"]["priceList"]
        if price_list is None:
            raise ShopifyError("Price list não encontrada")
        variants = result["data"]["nodes"]
        missing = [variant_id for variant_id, node in zip(variant_ids, variants, strict=True) if node is None]
        if missing:
            raise ShopifyError("Uma ou mais variantes não foram encontradas", details={"missingIds": missing})
        current = [(price_list.get(f"price{index}") or {}).get("nodes", []) for index in range(len(variant_ids))]
        return {"priceList": {key: price_list.get(key) for key in ("id", "name", "currency", "fixedPricesCount", "catalog", "parent")}, "variants": variants, "currentFixedPrices": [items[0] if items else None for items in current]}

    async def prepare_fixed_prices_add(self, args: dict[str, Any]) -> dict[str, Any]:
        prices = args["prices"]
        variant_ids = [item["variantId"] for item in prices]
        if len(set(variant_ids)) != len(variant_ids):
            raise ValueError("Cada variante pode aparecer apenas uma vez")
        preview = await self._fixed_prices_preview(args["priceListId"], variant_ids)
        expected_currency = preview["priceList"]["currency"]
        for item in prices:
            money_values = [item["price"]] + ([item["compareAtPrice"]] if item.get("compareAtPrice") else [])
            if any(money["currencyCode"] != expected_currency for money in money_values):
                raise ShopifyError("A moeda de todos os preços deve coincidir com a price list", details={"expectedCurrency": expected_currency})
        mutation_args = {"priceListId": args["priceListId"], "prices": prices}
        token = self.confirmations.issue("shopify_fixed_prices_add", mutation_args)
        return {**preview, "requestedPrices": prices, "willReplaceExisting": sum(item is not None for item in preview["currentFixedPrices"]), **token}

    async def fixed_prices_add(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"priceListId": args["priceListId"], "prices": args["prices"]}
        self._require_write(args, "shopify_fixed_prices_add", mutation_args)
        query = """mutation FixedPricesAdd($priceListId:ID!,$prices:[PriceListPriceInput!]!){priceListFixedPricesAdd(priceListId:$priceListId,prices:$prices){prices{price{amount currencyCode} compareAtPrice{amount currencyCode} originType variant{id title}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "priceListFixedPricesAdd", **mutation_result(result, "priceListFixedPricesAdd")}

    async def prepare_fixed_prices_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        preview = await self._fixed_prices_preview(args["priceListId"], args["variantIds"])
        mutation_args = {"priceListId": args["priceListId"], "variantIds": args["variantIds"]}
        token = self.confirmations.issue("shopify_fixed_prices_delete", mutation_args)
        return {**preview, "willDelete": sum(item is not None for item in preview["currentFixedPrices"]), "warnings": ["Variantes sem preço fixo voltarão ou permanecerão no ajuste padrão da price list."], **token}

    async def fixed_prices_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"priceListId": args["priceListId"], "variantIds": args["variantIds"]}
        self._require_write(args, "shopify_fixed_prices_delete", mutation_args)
        query = """mutation FixedPricesDelete($priceListId:ID!,$variantIds:[ID!]!){priceListFixedPricesDelete(priceListId:$priceListId,variantIds:$variantIds){deletedFixedPriceVariantIds userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "priceListFixedPricesDelete", **mutation_result(result, "priceListFixedPricesDelete")}

    _WEBHOOK_FIELDS = """id name topic uri format filter includeFields metafieldNamespaces createdAt updatedAt apiVersion{displayName handle supported}"""

    async def list_webhook_subscriptions(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Webhooks($first:Int!,$after:String,$query:String){{webhookSubscriptions(first:$first,after:$after,query:$query){{edges{{cursor node{{{self._WEBHOOK_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "webhookSubscriptions")

    async def get_webhook_subscription(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query Webhook($id:ID!){{webhookSubscription(id:$id){{{self._WEBHOOK_FIELDS}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        return {"webhookSubscription": result["data"]["webhookSubscription"]}

    @staticmethod
    def _validate_webhook_uri(uri: str) -> None:
        if not uri.startswith("https://"):
            return
        parsed = urlsplit(uri)
        hostname = (parsed.hostname or "").lower().rstrip(".")
        if not hostname or parsed.username or parsed.password:
            raise ValueError("Endpoint HTTPS deve ter hostname e não pode conter credenciais")
        if hostname == "localhost" or hostname.endswith((".localhost", ".local", ".internal")):
            raise ValueError("Endpoint local ou interno não é permitido")
        try:
            address = ipaddress.ip_address(hostname.strip("[]"))
        except ValueError:
            return
        if not address.is_global:
            raise ValueError("Endpoint deve usar endereço IP público")

    @staticmethod
    def _webhook_input(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("uri", "format", "filter", "includeFields", "metafieldNamespaces", "name") if key in args}

    async def prepare_webhook_create(self, args: dict[str, Any]) -> dict[str, Any]:
        self._validate_webhook_uri(args["uri"])
        webhook = self._webhook_input(args)
        result = await self.client.graphql("query ExistingWebhook($topics:[WebhookSubscriptionTopic!],$uri:String){webhookSubscriptions(first:10,topics:$topics,uri:$uri){nodes{id topic uri format filter}}}", {"topics": [args["topic"]], "uri": args["uri"]})
        if result["data"]["webhookSubscriptions"]["nodes"]:
            raise ShopifyError("Já existe uma subscription para esse tópico e URI")
        mutation_args = {"topic": args["topic"], "webhookSubscription": webhook}
        token = self.confirmations.issue("shopify_webhook_create", mutation_args)
        return {"willCreate": mutation_args, "consumerRequirements": ["Validar X-Shopify-Hmac-Sha256 sobre o corpo bruto com comparação constante.", "Deduplicar usando X-Shopify-Event-Id.", "Responder 2xx rapidamente e processar de forma assíncrona.", "Tratar entrega fora de ordem e retries como normais."], **token}

    async def webhook_create(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"topic": args["topic"], "webhookSubscription": self._webhook_input(args)}
        self._require_write(args, "shopify_webhook_create", mutation_args)
        query = f"mutation WebhookCreate($topic:WebhookSubscriptionTopic!,$webhookSubscription:WebhookSubscriptionInput!){{webhookSubscriptionCreate(topic:$topic,webhookSubscription:$webhookSubscription){{webhookSubscription{{{self._WEBHOOK_FIELDS}}} userErrors{{field message}}}}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "webhookSubscriptionCreate", **mutation_result(result, "webhookSubscriptionCreate")}

    async def prepare_webhook_update(self, args: dict[str, Any]) -> dict[str, Any]:
        current = (await self.get_webhook_subscription({"id": args["id"]}))["webhookSubscription"]
        if current is None:
            raise ShopifyError("Webhook subscription não encontrada")
        webhook = self._webhook_input(args)
        if not webhook:
            raise ValueError("Informe ao menos uma alteração para a subscription")
        if "uri" in webhook:
            self._validate_webhook_uri(webhook["uri"])
        mutation_args = {"id": args["id"], "webhookSubscription": webhook}
        token = self.confirmations.issue("shopify_webhook_update", mutation_args)
        return {"before": current, "requestedChanges": webhook, **token}

    async def webhook_update(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "webhookSubscription": self._webhook_input(args)}
        self._require_write(args, "shopify_webhook_update", mutation_args)
        query = f"mutation WebhookUpdate($id:ID!,$webhookSubscription:WebhookSubscriptionInput!){{webhookSubscriptionUpdate(id:$id,webhookSubscription:$webhookSubscription){{webhookSubscription{{{self._WEBHOOK_FIELDS}}} userErrors{{field message}}}}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "webhookSubscriptionUpdate", **mutation_result(result, "webhookSubscriptionUpdate")}

    async def prepare_webhook_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        current = (await self.get_webhook_subscription(args))["webhookSubscription"]
        if current is None:
            raise ShopifyError("Webhook subscription não encontrada")
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_webhook_delete", mutation_args)
        return {"webhookSubscription": current, "warnings": ["A Shopify deixará de enviar eventos futuros deste tópico para o endpoint."], **token}

    async def webhook_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_webhook_delete", mutation_args)
        result = await self.client.graphql("mutation WebhookDelete($id:ID!){webhookSubscriptionDelete(id:$id){deletedWebhookSubscriptionId userErrors{field message}}}", mutation_args)
        return {"success": True, "operation": "webhookSubscriptionDelete", **mutation_result(result, "webhookSubscriptionDelete")}

    _BULK_OPERATION_FIELDS = """id type status errorCode createdAt completedAt objectCount rootObjectCount fileSize url partialDataUrl"""

    async def list_bulk_operations(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query BulkOperations($first:Int!,$after:String,$query:String){{bulkOperations(first:$first,after:$after,query:$query,sortKey:CREATED_AT,reverse:true){{edges{{cursor node{{{self._BULK_OPERATION_FIELDS}}}}}pageInfo{{hasNextPage endCursor}}}}}}"
        result = await self.client.graphql(query, {"first": _page_size(args.get("first")), "after": args.get("after"), "query": args.get("query")})
        return _connection(result["data"], "bulkOperations")

    async def get_bulk_operation(self, args: dict[str, Any]) -> dict[str, Any]:
        query = f"query BulkOperation($id:ID!){{bulkOperation(id:$id){{{self._BULK_OPERATION_FIELDS}}}}}"
        result = await self.client.graphql(query, {"id": args["id"]})
        operation = result["data"]["bulkOperation"]
        return {"bulkOperation": operation, "resultFormat": "JSONL", "urlRetention": "7 days after completion", "downloadedByMcp": False}

    @staticmethod
    def _bulk_export_document(args: dict[str, Any]) -> str:
        resource = args["resource"]
        metaobject_type = args.get("metaobjectType")
        if resource == "METAOBJECTS" and not metaobject_type:
            raise ValueError("metaobjectType é obrigatório para exportar METAOBJECTS")
        if resource != "METAOBJECTS" and metaobject_type is not None:
            raise ValueError("metaobjectType só pode ser usado com METAOBJECTS")
        filters = []
        if args.get("query"):
            filters.append(f"query:{json.dumps(args['query'], ensure_ascii=False)}")
        suffix = f"({','.join(filters)})" if filters else ""
        documents = {
            "PRODUCTS": f"{{products{suffix}{{edges{{node{{id title handle descriptionHtml status vendor productType tags createdAt updatedAt totalInventory seo{{title description}} options{{id name position optionValues{{id name hasVariants}}}} variants{{edges{{node{{id title sku barcode price compareAtPrice inventoryQuantity inventoryPolicy taxable requiresComponents selectedOptions{{name value}} inventoryItem{{id tracked requiresShipping}} productVariantComponents{{edges{{node{{quantity productVariant{{id sku title price product{{id title handle}}}}}}}}}}}}}}}}}}}}}}}}",
            "PRODUCT_VARIANTS": f"{{productVariants{suffix}{{edges{{node{{id title displayName sku barcode price compareAtPrice inventoryQuantity inventoryPolicy taxable availableForSale selectedOptions{{name value}} product{{id title handle status}} inventoryItem{{id tracked requiresShipping}}}}}}}}}}",
            "COLLECTIONS": f"{{collections{suffix}{{edges{{node{{id title handle descriptionHtml sortOrder updatedAt productsCount{{count}} seo{{title description}} ruleSet{{appliedDisjunctively rules{{column relation condition conditionObject{{... on CollectionRuleMetafieldCondition{{metafieldDefinition{{id namespace key}}}}}}}}}}}}}}}}}}",
            "ORDERS": f"{{orders{suffix}{{edges{{node{{id name createdAt processedAt cancelledAt displayFinancialStatus currencyCode subtotalPriceSet{{shopMoney{{amount}}}} totalShippingPriceSet{{shopMoney{{amount}}}} totalDiscountsSet{{shopMoney{{amount}}}} currentTotalPriceSet{{shopMoney{{amount}}}} totalRefundedSet{{shopMoney{{amount}}}} discountCodes customAttributes{{key value}} lineItems{{edges{{node{{id discountAllocations{{allocatedAmountSet{{shopMoney{{amount}}}} discountApplication{{__typename value{{__typename ... on MoneyV2{{amount}} ... on PricingPercentageValue{{percentage}}}} ... on DiscountCodeApplication{{code}} ... on AutomaticDiscountApplication{{title}} ... on ManualDiscountApplication{{title}} ... on ScriptDiscountApplication{{title}}}}}}}}}}}}}}}}}}}}",
            "CUSTOMERS": f"{{customers{suffix}{{edges{{node{{id firstName lastName displayName email phone tags state createdAt updatedAt numberOfOrders amountSpent{{amount currencyCode}} defaultAddress{{id address1 address2 city provinceCode countryCodeV2 zip}}}}}}}}}}",
            "INVENTORY_ITEMS": f"{{inventoryItems{suffix}{{edges{{node{{id sku tracked requiresShipping createdAt updatedAt variant{{id title product{{id}}}} inventoryLevels{{edges{{node{{id location{{id name}} quantities(names:[\"available\",\"on_hand\",\"committed\",\"reserved\",\"incoming\",\"damaged\",\"safety_stock\",\"quality_control\"]){{name quantity}}}}}}}}}}}}}}}}",
            "METAOBJECTS": f"{{metaobjects(type:{json.dumps(metaobject_type, ensure_ascii=False)}{',' + ','.join(filters) if filters else ''}){{edges{{node{{id type handle displayName updatedAt capabilities{{publishable{{status}}}} fields{{key type value reference{{id}} references{{edges{{node{{id}}}}}}}}}}}}}}}}",
        }
        return documents[resource]

    @staticmethod
    def _bulk_export_args(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("resource", "query", "metaobjectType", "groupObjects") if key in args}

    def _guard_bulk_export_pii(self, resource: str) -> None:
        if resource == "CUSTOMERS" and self.client.settings.tool_profile != "full":
            raise ShopifyError("Exportação de CUSTOMERS exige o perfil full (contém PII).")

    async def prepare_bulk_export(self, args: dict[str, Any]) -> dict[str, Any]:
        self._guard_bulk_export_pii(args["resource"])
        document = self._bulk_export_document(args)
        mutation_args = self._bulk_export_args(args)
        token = self.confirmations.issue("shopify_start_bulk_export", mutation_args)
        warnings = ["O resultado é JSONL e as URLs expiram sete dias após a conclusão.", "O MCP não baixa nem persiste o arquivo retornado."]
        if args["resource"] in {"ORDERS", "CUSTOMERS"}:
            warnings.append("A exportação contém PII; aplique minimização, controle de acesso, retenção e LGPD.")
        if args.get("groupObjects", False):
            warnings.append("groupObjects=true reduz desempenho e aumenta o risco de timeout.")
        return {"willStart": mutation_args, "documentKind": "curated", "graphqlAcceptedFromCaller": False, "estimatedConnections": document.count("edges{"), "warnings": warnings, **token}

    async def start_bulk_export(self, args: dict[str, Any]) -> dict[str, Any]:
        self._guard_bulk_export_pii(args["resource"])
        mutation_args = self._bulk_export_args(args)
        self._require_write(args, "shopify_start_bulk_export", mutation_args)
        document = self._bulk_export_document(args)
        variables = {"query": document, "groupObjects": args.get("groupObjects", False)}
        query = f"mutation BulkExport($query:String!,$groupObjects:Boolean!){{bulkOperationRunQuery(query:$query,groupObjects:$groupObjects){{bulkOperation{{{self._BULK_OPERATION_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, variables)
        return {"success": True, "operation": "bulkOperationRunQuery", "resource": args["resource"], "resultFormat": "JSONL", **mutation_result(result, "bulkOperationRunQuery")}

    async def prepare_bulk_operation_cancel(self, args: dict[str, Any]) -> dict[str, Any]:
        operation = (await self.get_bulk_operation(args))["bulkOperation"]
        if operation is None:
            raise ShopifyError("Bulk operation não encontrada")
        if operation["status"] not in {"CREATED", "RUNNING"}:
            raise ShopifyError("Somente jobs CREATED ou RUNNING podem ser cancelados", details={"status": operation["status"]})
        mutation_args = {"id": args["id"]}
        token = self.confirmations.issue("shopify_cancel_bulk_operation", mutation_args)
        return {"bulkOperation": operation, "warnings": ["O cancelamento é assíncrono e pode permanecer em CANCELING por algum tempo.", "Dados parciais podem ficar disponíveis em partialDataUrl."], **token}

    async def cancel_bulk_operation(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"]}
        self._require_write(args, "shopify_cancel_bulk_operation", mutation_args)
        query = f"mutation BulkCancel($id:ID!){{bulkOperationCancel(id:$id){{bulkOperation{{{self._BULK_OPERATION_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "bulkOperationCancel", **mutation_result(result, "bulkOperationCancel")}

    async def prepare_bulk_import_staged_upload(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"input": [{"filename": args["filename"], "mimeType": "text/jsonl", "resource": "BULK_MUTATION_VARIABLES", "httpMethod": "POST", "fileSize": args["fileSize"]}]}
        token = self.confirmations.issue("shopify_create_bulk_import_staged_upload", mutation_args)
        return {"uploadMetadata": mutation_args["input"][0], "requirements": ["Enviar multipart/form-data diretamente ao URL retornado.", "Manter os parâmetros na ordem retornada e anexar file por último.", "Não alterar o objeto staged depois do upload."], **token}

    async def create_bulk_import_staged_upload(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"input": [{"filename": args["filename"], "mimeType": "text/jsonl", "resource": "BULK_MUTATION_VARIABLES", "httpMethod": "POST", "fileSize": args["fileSize"]}]}
        self._require_write(args, "shopify_create_bulk_import_staged_upload", mutation_args)
        result = await self.client.graphql("mutation BulkImportStage($input:[StagedUploadInput!]!){stagedUploadsCreate(input:$input){stagedTargets{url resourceUrl parameters{name value}} userErrors{field message}}}", mutation_args)
        return {"success": True, "operation": "stagedUploadsCreate", "transportedByMcp": False, **mutation_result(result, "stagedUploadsCreate")}

    _BULK_IMPORT_MUTATIONS = {
        "PRODUCT_CREATE": "mutation BulkProductCreate($product:ProductCreateInput!){productCreate(product:$product){product{id title handle status} userErrors{field message}}}",
        "PRODUCT_UPDATE": "mutation BulkProductUpdate($product:ProductUpdateInput!){productUpdate(product:$product){product{id title handle status updatedAt} userErrors{field message}}}",
        "PRODUCT_VARIANTS_BULK_UPDATE": "mutation BulkVariantsUpdate($productId:ID!,$variants:[ProductVariantsBulkInput!]!){productVariantsBulkUpdate(productId:$productId,variants:$variants,allowPartialUpdates:false){productVariants{id barcode sku updatedAt} userErrors{field message code}}}",
        "PUBLISHABLE_PUBLISH": "mutation BulkPublish($id:ID!,$input:[PublicationInput!]!){publishablePublish(id:$id,input:$input){publishable{... on Product{id title} resourcePublicationsCount{count}} userErrors{field message}}}",
        "PUBLISHABLE_UNPUBLISH": "mutation BulkUnpublish($id:ID!,$input:[PublicationInput!]!){publishableUnpublish(id:$id,input:$input){publishable{... on Product{id title} resourcePublicationsCount{count}} userErrors{field message}}}",
        "TAGS_ADD": "mutation BulkTagsAdd($id:ID!,$tags:[String!]!){tagsAdd(id:$id,tags:$tags){node{id} userErrors{field message}}}",
        "TAGS_REMOVE": "mutation BulkTagsRemove($id:ID!,$tags:[String!]!){tagsRemove(id:$id,tags:$tags){node{id} userErrors{field message}}}",
        "METAFIELDS_SET": "mutation BulkMetafieldsSet($metafields:[MetafieldsSetInput!]!){metafieldsSet(metafields:$metafields){metafields{id ownerType namespace key type compareDigest updatedAt} userErrors{field message code}}}",
        "METAOBJECT_CREATE": "mutation BulkMetaobjectCreate($metaobject:MetaobjectCreateInput!){metaobjectCreate(metaobject:$metaobject){metaobject{id type handle updatedAt} userErrors{field message code elementIndex elementKey}}}",
        "METAOBJECT_UPDATE": "mutation BulkMetaobjectUpdate($id:ID!,$metaobject:MetaobjectUpdateInput!){metaobjectUpdate(id:$id,metaobject:$metaobject){metaobject{id type handle updatedAt} userErrors{field message code elementIndex elementKey}}}",
    }
    _BULK_IMPORT_VARIABLES = {
        "PRODUCT_CREATE": {"product": "ProductCreateInput!"},
        "PRODUCT_UPDATE": {"product": "ProductUpdateInput!"},
        "PRODUCT_VARIANTS_BULK_UPDATE": {"productId": "ID!", "variants": "[ProductVariantsBulkInput!]! (uma linha por produto; atomico por linha)"},
        "PUBLISHABLE_PUBLISH": {"id": "ID!", "input": "[PublicationInput!]! (uma linha por produto/coleção; publicationId por canal)"},
        "PUBLISHABLE_UNPUBLISH": {"id": "ID!", "input": "[PublicationInput!]! (uma linha por produto/coleção; publicationId por canal)"},
        "TAGS_ADD": {"id": "ID!", "tags": "[String!]! (só acrescenta; nunca substitui o conjunto)"},
        "TAGS_REMOVE": {"id": "ID!", "tags": "[String!]! (só remove as listadas)"},
        "METAFIELDS_SET": {"metafields": "[MetafieldsSetInput!]! (máximo 25 por linha; use compareDigest)"},
        "METAOBJECT_CREATE": {"metaobject": "MetaobjectCreateInput!"},
        "METAOBJECT_UPDATE": {"id": "ID!", "metaobject": "MetaobjectUpdateInput!"},
    }

    @staticmethod
    def _bulk_import_args(args: dict[str, Any]) -> dict[str, Any]:
        return {key: args[key] for key in ("kind", "stagedUploadPath", "clientIdentifier", "lineCount", "sha256", "acknowledgeUnorderedExecution")}

    async def prepare_bulk_import(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = self._bulk_import_args(args)
        token = self.confirmations.issue("shopify_start_bulk_import", mutation_args)
        warnings = ["O MCP vincula o hash declarado, mas não lê o JSONL e portanto não consegue verificá-lo.", "Linhas são independentes, podem executar fora de ordem e podem ter sucesso parcial.", "Baixe e reconcilie o JSONL de resultado antes de considerar a integração concluída."]
        if args["kind"] == "METAFIELDS_SET":
            warnings.append("Inclua compareDigest em updates para evitar sobrescrita concorrente; omiti-lo enfraquece CAS.")
        return {"willStart": mutation_args, "variablesPerJsonlLine": self._BULK_IMPORT_VARIABLES[args["kind"]], "graphqlAcceptedFromCaller": False, "warnings": warnings, **token}

    async def start_bulk_import(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = self._bulk_import_args(args)
        self._require_write(args, "shopify_start_bulk_import", mutation_args)
        variables = {"mutation": self._BULK_IMPORT_MUTATIONS[args["kind"]], "stagedUploadPath": args["stagedUploadPath"], "clientIdentifier": args["clientIdentifier"]}
        query = f"mutation BulkImport($mutation:String!,$stagedUploadPath:String!,$clientIdentifier:String){{bulkOperationRunMutation(mutation:$mutation,stagedUploadPath:$stagedUploadPath,clientIdentifier:$clientIdentifier){{bulkOperation{{{self._BULK_OPERATION_FIELDS}}} userErrors{{field message code}}}}}}"
        result = await self.client.graphql(query, variables)
        return {"success": True, "operation": "bulkOperationRunMutation", "kind": args["kind"], "declaredInput": {"lineCount": args["lineCount"], "sha256": args["sha256"]}, "resultFormat": "JSONL", **mutation_result(result, "bulkOperationRunMutation")}

    async def prepare_tags_change(self, args: dict[str, Any]) -> dict[str, Any]:
        query = """query Taggable($id:ID!){node(id:$id){id __typename ... on Product{tags} ... on Customer{tags} ... on Order{tags} ... on DraftOrder{tags}}}"""
        result = await self.client.graphql(query, {"id": args["id"]})
        node = result["data"]["node"]
        if node is None or "tags" not in node:
            raise ShopifyError("Recurso não encontrado ou não suportado para tags")
        current = list(node.get("tags") or [])
        requested = args["tags"]
        action = args["action"]
        if action == "add":
            after = current + [tag for tag in requested if tag not in current]
            tool = "shopify_add_tags"
        else:
            remove = set(requested)
            after = [tag for tag in current if tag not in remove]
            tool = "shopify_remove_tags"
        mutation_args = {"id": args["id"], "tags": requested}
        token = self.confirmations.issue(tool, mutation_args)
        return {"operation": tool, "resourceType": node["__typename"], "before": current, "after": after, "willChange": before_changed(current, after), **token}

    async def prepare_product_seo_update(self, args: dict[str, Any]) -> dict[str, Any]:
        seo = {key: args[key] for key in ("title", "description") if args.get(key) is not None}
        if not seo:
            raise ValueError("Informe title e/ou description")
        result = await self.client.graphql("""query ProductSeoPreview($id:ID!){product(id:$id){id title handle seo{title description}}}""", {"id": args["id"]})
        product = result["data"]["product"]
        if product is None:
            raise ShopifyError("Produto não encontrado")
        before = product.get("seo") or {}
        after = {**before, **seo}
        mutation_args = {"id": args["id"], **seo}
        token = self.confirmations.issue("shopify_update_product_seo", mutation_args)
        return {"product": {"id": product["id"], "title": product["title"], "handle": product["handle"]}, "before": before, "after": after, "willChange": before_changed(before, after), **token}

    async def prepare_product_create(self, args: dict[str, Any]) -> dict[str, Any]:
        product_input = _product_input(args, include_id=False)
        token = self.confirmations.issue("shopify_create_product", product_input)
        return {
            "operation": "shopify_create_product",
            "before": None,
            "after": product_input,
            "warnings": ["O produto é criado sem publicação; publique separadamente após validar cadastro e variantes."],
            **token,
        }

    async def create_product(self, args: dict[str, Any]) -> dict[str, Any]:
        product_input = _product_input(args, include_id=False)
        self._require_write(args, "shopify_create_product", product_input)
        query = """mutation ProductCreate($product:ProductCreateInput!){productCreate(product:$product){product{id title handle status vendor productType tags seo{title description} options{id name position optionValues{id name hasVariants}} variants(first:10){nodes{id title sku price selectedOptions{name value}}}} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"product": product_input})
        return {"success": True, "operation": "productCreate", **mutation_result(result, "productCreate")}

    async def prepare_product_update(self, args: dict[str, Any]) -> dict[str, Any]:
        changes = _product_input(args, include_id=False)
        if not changes:
            raise ValueError("Informe ao menos um campo para alterar")
        requested_collection_ids = list(dict.fromkeys(changes.get("collectionsToJoin", []) + changes.get("collectionsToLeave", [])))
        if set(changes.get("collectionsToJoin", [])) & set(changes.get("collectionsToLeave", [])):
            raise ValueError("A mesma coleção não pode ser adicionada e removida na mesma operação")
        result = await self.client.graphql("""query ProductUpdatePreview($id:ID!,$collectionIds:[ID!]!){product(id:$id){id title descriptionHtml handle vendor productType status category{id} tags seo{title description} templateSuffix requiresSellingPlan collections(first:250){nodes{id title handle}}} nodes(ids:$collectionIds){... on Collection{id title handle}}}""", {"id": args["id"], "collectionIds": requested_collection_ids})
        product = result["data"]["product"]
        if product is None:
            raise ShopifyError("Produto não encontrado")
        found_collections = {node["id"] for node in result["data"].get("nodes", []) if node}
        missing_collections = sorted(set(requested_collection_ids) - found_collections)
        if missing_collections:
            raise ShopifyError("Uma ou mais coleções não foram encontradas", details={"missingIds": missing_collections})
        before = {
            "title": product.get("title"), "descriptionHtml": product.get("descriptionHtml"),
            "handle": product.get("handle"), "vendor": product.get("vendor"),
            "productType": product.get("productType"), "status": product.get("status"),
            "category": (product.get("category") or {}).get("id"), "tags": product.get("tags"),
            "seo": product.get("seo"), "templateSuffix": product.get("templateSuffix"),
            "requiresSellingPlan": product.get("requiresSellingPlan"),
            "collections": product.get("collections", {}).get("nodes", []),
        }
        after = {**before, **{key: value for key, value in changes.items() if key not in {"collectionsToJoin", "collectionsToLeave"}}}
        if requested_collection_ids:
            current = {item["id"]: item for item in before["collections"]}
            for collection_id in changes.get("collectionsToLeave", []):
                current.pop(collection_id, None)
            found_nodes = {node["id"]: node for node in result["data"].get("nodes", []) if node}
            for collection_id in changes.get("collectionsToJoin", []):
                current[collection_id] = found_nodes[collection_id]
            after["collections"] = list(current.values())
        mutation_input = {"id": args["id"], **changes}
        token = self.confirmations.issue("shopify_update_product", mutation_input)
        return {"product": {"id": product["id"], "title": product["title"]}, "before": before, "after": after, "willChange": before_changed(before, after), **token}

    async def update_product(self, args: dict[str, Any]) -> dict[str, Any]:
        product_input = _product_input(args, include_id=True)
        self._require_write(args, "shopify_update_product", product_input)
        query = """mutation ProductUpdate($product:ProductUpdateInput!){productUpdate(product:$product){product{id title handle status vendor productType tags category{id fullName} seo{title description} updatedAt} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"product": product_input})
        return {"success": True, "operation": "productUpdate", **mutation_result(result, "productUpdate")}

    async def prepare_variants_bulk_create(self, args: dict[str, Any]) -> dict[str, Any]:
        result = await self.client.graphql("""query VariantCreatePreview($id:ID!){product(id:$id){id title handle options{id name position optionValues{id name hasVariants}} variants(first:20){nodes{id title inventoryItem{sku} selectedOptions{name value}}}}}""", {"id": args["productId"]})
        product = result["data"]["product"]
        if product is None:
            raise ShopifyError("Produto não encontrado")
        mutation_args = {"productId": args["productId"], "strategy": args["strategy"], "variants": args["variants"]}
        token = self.confirmations.issue("shopify_variants_bulk_create", mutation_args)
        warnings = []
        if args["strategy"] in {"DEFAULT", "REMOVE_STANDALONE_VARIANT"}:
            warnings.append("A estratégia pode remover a variante standalone existente; revise before cuidadosamente.")
        return {
            "product": {"id": product["id"], "title": product["title"], "handle": product["handle"]},
            "before": {"options": product["options"], "variants": product["variants"]["nodes"]},
            "willCreate": len(args["variants"]), "strategy": args["strategy"], "warnings": warnings, **token,
        }

    async def variants_bulk_create(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"productId": args["productId"], "strategy": args["strategy"], "variants": args["variants"]}
        self._require_write(args, "shopify_variants_bulk_create", mutation_args)
        query = """mutation VariantsBulkCreate($productId:ID!,$strategy:ProductVariantsBulkCreateStrategy!,$variants:[ProductVariantsBulkInput!]!){productVariantsBulkCreate(productId:$productId,strategy:$strategy,variants:$variants){product{id title options{id name position optionValues{id name hasVariants}}} productVariants{id title price compareAtPrice inventoryItem{id sku tracked requiresShipping} selectedOptions{name value}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        payload = mutation_result(result, "productVariantsBulkCreate")
        return {"success": True, "operation": "productVariantsBulkCreate", "summary": {"requested": len(args["variants"]), "created": len(payload.get("productVariants") or [])}, **payload}

    async def prepare_variants_bulk_update(self, args: dict[str, Any]) -> dict[str, Any]:
        ids = [variant["id"] for variant in args["variants"]]
        if len(set(ids)) != len(ids):
            raise ValueError("Cada variante pode aparecer apenas uma vez no lote")
        if any(set(variant) == {"id"} for variant in args["variants"]):
            raise ValueError("Cada variante deve informar ao menos um campo para alterar")
        result = await self.client.graphql("""query VariantUpdatePreview($ids:[ID!]!){nodes(ids:$ids){... on ProductVariant{id title sku:inventoryItem{sku} barcode price compareAtPrice inventoryPolicy taxable requiresComponents product{id} selectedOptions{name value}}}}""", {"ids": ids})
        nodes = result["data"]["nodes"]
        found = {node["id"]: node for node in nodes if node}
        missing = [variant_id for variant_id in ids if variant_id not in found]
        wrong_product = [node["id"] for node in found.values() if node["product"]["id"] != args["productId"]]
        if missing:
            raise ShopifyError("Uma ou mais variantes não foram encontradas", details={"missingIds": missing})
        if wrong_product:
            raise ShopifyError("Uma ou mais variantes não pertencem ao produto informado", details={"variantIds": wrong_product})
        mutation_args = {"productId": args["productId"], "variants": args["variants"]}
        token = self.confirmations.issue("shopify_variants_bulk_update", mutation_args)
        return {"before": [found[variant_id] for variant_id in ids], "requestedChanges": args["variants"], "atomic": True, "willUpdate": len(ids), **token}

    async def variants_bulk_update(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"productId": args["productId"], "variants": args["variants"]}
        self._require_write(args, "shopify_variants_bulk_update", mutation_args)
        query = """mutation VariantsBulkUpdate($productId:ID!,$variants:[ProductVariantsBulkInput!]!){productVariantsBulkUpdate(productId:$productId,variants:$variants,allowPartialUpdates:false){product{id title} productVariants{id title price compareAtPrice barcode inventoryPolicy taxable inventoryItem{id sku tracked requiresShipping} selectedOptions{name value}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        payload = mutation_result(result, "productVariantsBulkUpdate")
        return {"success": True, "operation": "productVariantsBulkUpdate", "summary": {"requested": len(args["variants"]), "updated": len(payload.get("productVariants") or []), "atomic": True}, **payload}

    async def _option_preview(self, product_id: str) -> dict[str, Any]:
        query = """query ProductOptionPreview($id:ID!){product(id:$id){id title handle options{id name position optionValues{id name hasVariants}} variants(first:100){nodes{id title selectedOptions{name value}}}}}"""
        result = await self.client.graphql(query, {"id": product_id})
        product = result["data"]["product"]
        if product is None:
            raise ShopifyError("Produto não encontrado")
        return product

    async def prepare_product_options_create(self, args: dict[str, Any]) -> dict[str, Any]:
        product = await self._option_preview(args["productId"])
        if len(product["options"]) + len(args["options"]) > 3:
            raise ValueError("Um produto pode ter no máximo 3 opções")
        mutation_args = {key: args[key] for key in ("productId", "options", "variantStrategy")}
        token = self.confirmations.issue("shopify_product_options_create", mutation_args)
        warnings = []
        if args["variantStrategy"] == "CREATE":
            warnings.append("CREATE gera combinações adicionais de variantes e está sujeito ao limite da loja.")
        return {"product": {"id": product["id"], "title": product["title"]}, "before": {"options": product["options"], "variants": product["variants"]["nodes"]}, "requestedOptions": args["options"], "variantStrategy": args["variantStrategy"], "warnings": warnings, **token}

    async def product_options_create(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {key: args[key] for key in ("productId", "options", "variantStrategy")}
        self._require_write(args, "shopify_product_options_create", mutation_args)
        query = """mutation ProductOptionsCreate($productId:ID!,$options:[OptionCreateInput!]!,$variantStrategy:ProductOptionCreateVariantStrategy!){productOptionsCreate(productId:$productId,options:$options,variantStrategy:$variantStrategy){product{id title options{id name position optionValues{id name hasVariants}} variants(first:100){nodes{id title selectedOptions{name value}}}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "productOptionsCreate", **mutation_result(result, "productOptionsCreate")}

    async def prepare_product_option_update(self, args: dict[str, Any]) -> dict[str, Any]:
        product = await self._option_preview(args["productId"])
        option = next((item for item in product["options"] if item["id"] == args["optionId"]), None)
        if option is None:
            raise ShopifyError("A opção não pertence ao produto informado")
        changes = {key: args[key] for key in ("name", "position", "valuesToAdd", "valuesToUpdate", "valueIdsToDelete") if key in args}
        if not changes:
            raise ValueError("Informe ao menos uma alteração para a opção")
        known_values = {item["id"] for item in option["optionValues"]}
        referenced = {item["id"] for item in args.get("valuesToUpdate", [])} | set(args.get("valueIdsToDelete", []))
        if not referenced <= known_values:
            raise ShopifyError("Um ou mais valores não pertencem à opção informada", details={"invalidIds": sorted(referenced - known_values)})
        mutation_args = {"productId": args["productId"], "option": {"id": args["optionId"], **{key: args[key] for key in ("name", "position") if key in args}}, "variantStrategy": args["variantStrategy"]}
        for source, target in (("valuesToAdd", "optionValuesToAdd"), ("valuesToUpdate", "optionValuesToUpdate"), ("valueIdsToDelete", "optionValuesToDelete")):
            if source in args:
                mutation_args[target] = args[source]
        token = self.confirmations.issue("shopify_product_option_update", mutation_args)
        warnings = ["MANAGE pode criar variantes para valores adicionados e apagar variantes ligadas a valores removidos."] if args["variantStrategy"] == "MANAGE" else []
        return {"product": {"id": product["id"], "title": product["title"]}, "before": {"option": option, "variants": product["variants"]["nodes"]}, "requestedChanges": changes, "variantStrategy": args["variantStrategy"], "warnings": warnings, **token}

    async def product_option_update(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"productId": args["productId"], "option": {"id": args["optionId"], **{key: args[key] for key in ("name", "position") if key in args}}, "variantStrategy": args["variantStrategy"]}
        for source, target in (("valuesToAdd", "optionValuesToAdd"), ("valuesToUpdate", "optionValuesToUpdate"), ("valueIdsToDelete", "optionValuesToDelete")):
            if source in args:
                mutation_args[target] = args[source]
        self._require_write(args, "shopify_product_option_update", mutation_args)
        query = """mutation ProductOptionUpdate($productId:ID!,$option:OptionUpdateInput!,$optionValuesToAdd:[OptionValueCreateInput!],$optionValuesToUpdate:[OptionValueUpdateInput!],$optionValuesToDelete:[ID!],$variantStrategy:ProductOptionUpdateVariantStrategy!){productOptionUpdate(productId:$productId,option:$option,optionValuesToAdd:$optionValuesToAdd,optionValuesToUpdate:$optionValuesToUpdate,optionValuesToDelete:$optionValuesToDelete,variantStrategy:$variantStrategy){product{id title options{id name position optionValues{id name hasVariants}}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "productOptionUpdate", **mutation_result(result, "productOptionUpdate")}

    async def prepare_product_options_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        product = await self._option_preview(args["productId"])
        by_id = {item["id"]: item for item in product["options"]}
        missing = [option_id for option_id in args["optionIds"] if option_id not in by_id]
        if missing:
            raise ShopifyError("Uma ou mais opções não pertencem ao produto informado", details={"invalidIds": missing})
        mutation_args = {"productId": args["productId"], "options": args["optionIds"], "strategy": args["strategy"]}
        token = self.confirmations.issue("shopify_product_options_delete", mutation_args)
        warnings = ["A exclusão remove opções e valores associados."]
        if args["strategy"] == "POSITION":
            warnings.append("POSITION pode apagar variantes duplicadas, preservando as de menor posição.")
        return {"product": {"id": product["id"], "title": product["title"]}, "before": {"options": [by_id[item] for item in args["optionIds"]], "variants": product["variants"]["nodes"]}, "strategy": args["strategy"], "warnings": warnings, **token}

    async def product_options_delete(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"productId": args["productId"], "options": args["optionIds"], "strategy": args["strategy"]}
        self._require_write(args, "shopify_product_options_delete", mutation_args)
        query = """mutation ProductOptionsDelete($productId:ID!,$options:[ID!]!,$strategy:ProductOptionDeleteStrategy!){productOptionsDelete(productId:$productId,options:$options,strategy:$strategy){deletedOptionsIds product{id title options{id name position optionValues{id name hasVariants}}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "productOptionsDelete", **mutation_result(result, "productOptionsDelete")}

    async def prepare_product_options_reorder(self, args: dict[str, Any]) -> dict[str, Any]:
        product = await self._option_preview(args["productId"])
        current = {item["id"]: item for item in product["options"]}
        requested_ids = [item["id"] for item in args["options"]]
        if len(set(requested_ids)) != len(requested_ids) or set(requested_ids) != set(current):
            raise ValueError("Informe cada opção atual exatamente uma vez para definir a ordem completa")
        for item in args["options"]:
            if "values" in item:
                current_values = {value["id"] for value in current[item["id"]]["optionValues"]}
                requested_values = [value["id"] for value in item["values"]]
                if len(set(requested_values)) != len(requested_values) or set(requested_values) != current_values:
                    raise ValueError("Ao reordenar valores, informe cada valor atual exatamente uma vez")
        mutation_args = {"productId": args["productId"], "options": args["options"]}
        token = self.confirmations.issue("shopify_product_options_reorder", mutation_args)
        return {"product": {"id": product["id"], "title": product["title"]}, "before": {"options": product["options"], "variants": product["variants"]["nodes"]}, "requestedOrder": args["options"], "warnings": ["A ordem recalcula a apresentação das variantes."], **token}

    async def product_options_reorder(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"productId": args["productId"], "options": args["options"]}
        self._require_write(args, "shopify_product_options_reorder", mutation_args)
        query = """mutation ProductOptionsReorder($productId:ID!,$options:[OptionReorderInput!]!){productOptionsReorder(productId:$productId,options:$options){product{id title options{id name position optionValues{id name hasVariants}} variants(first:100){nodes{id title selectedOptions{name value}}}} userErrors{field message code}}}"""
        result = await self.client.graphql(query, mutation_args)
        return {"success": True, "operation": "productOptionsReorder", **mutation_result(result, "productOptionsReorder")}

    async def add_tags(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "tags": args["tags"]}
        self._require_write(args, "shopify_add_tags", mutation_args)
        query = """mutation AddTags($id:ID!,$tags:[String!]!){tagsAdd(id:$id,tags:$tags){node{id} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"id": args["id"], "tags": args["tags"]})
        return {"success": True, "operation": "tagsAdd", **mutation_result(result, "tagsAdd")}

    async def remove_tags(self, args: dict[str, Any]) -> dict[str, Any]:
        mutation_args = {"id": args["id"], "tags": args["tags"]}
        self._require_write(args, "shopify_remove_tags", mutation_args)
        query = """mutation RemoveTags($id:ID!,$tags:[String!]!){tagsRemove(id:$id,tags:$tags){node{id} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"id": args["id"], "tags": args["tags"]})
        return {"success": True, "operation": "tagsRemove", **mutation_result(result, "tagsRemove")}

    async def update_product_seo(self, args: dict[str, Any]) -> dict[str, Any]:
        seo = {k: args[k] for k in ("title", "description") if args.get(k) is not None}
        if not seo:
            raise ValueError("Informe title e/ou description")
        mutation_args = {"id": args["id"], **seo}
        self._require_write(args, "shopify_update_product_seo", mutation_args)
        query = """mutation ProductSeo($product:ProductUpdateInput!){productUpdate(product:$product){product{id title handle seo{title description}} userErrors{field message}}}"""
        result = await self.client.graphql(query, {"product": {"id": args["id"], "seo": seo}})
        return {"success": True, "operation": "productUpdate", **mutation_result(result, "productUpdate")}


def before_changed(before: Any, after: Any) -> bool:
    return before != after


def current_field_required(definition: dict[str, Any], key: str) -> bool:
    return bool(next(field for field in definition["fieldDefinitions"] if field["key"] == key).get("required"))
