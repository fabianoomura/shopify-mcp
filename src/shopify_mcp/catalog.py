from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import mcp.types as types

READ = types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True)
WRITE = types.ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
DESTRUCTIVE_WRITE = types.ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True)

PAGE = {
    "first": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25, "description": "Itens desta página."},
    "after": {"type": "string", "description": "Cursor endCursor da página anterior."},
}
SEARCH_PAGE = {**PAGE, "query": {"type": "string", "maxLength": 1000, "description": "Sintaxe de busca Shopify, por exemplo status:active ou sku:ABC."}}

SEO_INPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {"title": {"type": "string", "maxLength": 70}, "description": {"type": "string", "maxLength": 320}},
}
PRODUCT_OPTIONS_INPUT = {
    "type": "array", "minItems": 1, "maxItems": 3,
    "items": {
        "type": "object", "additionalProperties": False, "required": ["name", "values"],
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 255},
            "values": {"type": "array", "minItems": 1, "maxItems": 250, "items": {"type": "object", "additionalProperties": False, "required": ["name"], "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 255}}}},
        },
    },
}
PRODUCT_CREATE_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 255},
    "descriptionHtml": {"type": "string", "maxLength": 1000000},
    "handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255},
    "vendor": {"type": "string", "maxLength": 255}, "productType": {"type": "string", "maxLength": 255},
    "status": {"type": "string", "enum": ["ACTIVE", "ARCHIVED", "DRAFT", "UNLISTED"]},
    "categoryId": {"type": "string", "pattern": "^gid://shopify/TaxonomyCategory/[A-Za-z0-9_-]+$"},
    "tags": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 255}},
    "seo": SEO_INPUT, "templateSuffix": {"type": ["string", "null"], "maxLength": 255},
    "requiresSellingPlan": {"type": "boolean"}, "productOptions": PRODUCT_OPTIONS_INPUT,
}
PRODUCT_UPDATE_FIELDS = {
    **PRODUCT_CREATE_FIELDS,
    "redirectNewHandle": {"type": "boolean"},
    "collectionsToJoin": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "pattern": "^gid://shopify/Collection/[0-9]+$"}},
    "collectionsToLeave": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "pattern": "^gid://shopify/Collection/[0-9]+$"}},
}
MONEY = {"type": ["string", "null"], "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]{1,2})?$"}
OPTION_VALUE_INPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "id": {"type": "string", "pattern": "^gid://shopify/ProductOptionValue/[0-9]+$"},
        "name": {"type": "string", "minLength": 1, "maxLength": 255},
        "optionId": {"type": "string", "pattern": "^gid://shopify/ProductOption/[0-9]+$"},
        "optionName": {"type": "string", "minLength": 1, "maxLength": 255},
    }, "anyOf": [{"required": ["id"]}, {"required": ["name", "optionId"]}, {"required": ["name", "optionName"]}],
}
INVENTORY_ITEM_INPUT = {
    "type": "object", "additionalProperties": False,
    "properties": {"sku": {"type": ["string", "null"], "maxLength": 255}, "tracked": {"type": "boolean"}, "requiresShipping": {"type": "boolean"}},
}
VARIANT_COMMON_FIELDS = {
    "barcode": {"type": ["string", "null"], "maxLength": 255}, "price": MONEY, "compareAtPrice": MONEY,
    "inventoryPolicy": {"type": "string", "enum": ["CONTINUE", "DENY"]}, "inventoryItem": INVENTORY_ITEM_INPUT,
    "taxable": {"type": "boolean"}, "requiresComponents": {"type": "boolean"},
    "optionValues": {"type": "array", "minItems": 1, "maxItems": 3, "items": OPTION_VALUE_INPUT},
}
VARIANT_CREATE_ITEM = {"type": "object", "additionalProperties": False, "properties": VARIANT_COMMON_FIELDS, "required": ["optionValues"]}
VARIANT_UPDATE_ITEM = {"type": "object", "additionalProperties": False, "properties": {"id": {"type": "string", "pattern": "^gid://shopify/ProductVariant/[0-9]+$"}, **VARIANT_COMMON_FIELDS}, "required": ["id"]}
VARIANT_CREATE_FIELDS = {
    "productId": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"},
    "strategy": {"type": "string", "enum": ["DEFAULT", "PRESERVE_STANDALONE_VARIANT", "REMOVE_STANDALONE_VARIANT"]},
    "variants": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": VARIANT_CREATE_ITEM},
}
VARIANT_UPDATE_FIELDS = {
    "productId": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"},
    "variants": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": VARIANT_UPDATE_ITEM},
}
PRODUCT_ID = {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"}
OPTION_ID = {"type": "string", "pattern": "^gid://shopify/ProductOption/[0-9]+$"}
OPTION_VALUE_ID = {"type": "string", "pattern": "^gid://shopify/ProductOptionValue/[0-9]+$"}
OPTION_CREATE = {
    "type": "object", "additionalProperties": False, "required": ["name", "values"],
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 255},
        "position": {"type": "integer", "minimum": 1, "maximum": 3},
        "values": {"type": "array", "minItems": 1, "maxItems": 250, "uniqueItems": True,
                   "items": {"type": "object", "additionalProperties": False, "required": ["name"],
                             "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 255}}}},
    },
}
OPTIONS_CREATE_FIELDS = {
    "productId": PRODUCT_ID,
    "options": {"type": "array", "minItems": 1, "maxItems": 3, "uniqueItems": True, "items": OPTION_CREATE},
    "variantStrategy": {"type": "string", "enum": ["LEAVE_AS_IS", "CREATE"]},
}
OPTION_UPDATE_FIELDS = {
    "productId": PRODUCT_ID, "optionId": OPTION_ID,
    "name": {"type": "string", "minLength": 1, "maxLength": 255},
    "position": {"type": "integer", "minimum": 1, "maximum": 3},
    "valuesToAdd": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "object", "additionalProperties": False, "required": ["name"], "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 255}}}},
    "valuesToUpdate": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "object", "additionalProperties": False, "required": ["id", "name"], "properties": {"id": OPTION_VALUE_ID, "name": {"type": "string", "minLength": 1, "maxLength": 255}}}},
    "valueIdsToDelete": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": OPTION_VALUE_ID},
    "variantStrategy": {"type": "string", "enum": ["LEAVE_AS_IS", "MANAGE"]},
}
OPTIONS_DELETE_FIELDS = {
    "productId": PRODUCT_ID,
    "optionIds": {"type": "array", "minItems": 1, "maxItems": 3, "uniqueItems": True, "items": OPTION_ID},
    "strategy": {"type": "string", "enum": ["DEFAULT", "NON_DESTRUCTIVE", "POSITION"]},
}
OPTION_REORDER = {"type": "object", "additionalProperties": False, "required": ["id"], "properties": {
    "id": OPTION_ID,
    "values": {"type": "array", "minItems": 1, "maxItems": 250, "uniqueItems": True,
               "items": {"type": "object", "additionalProperties": False, "required": ["id"], "properties": {"id": OPTION_VALUE_ID}}},
}}
OPTIONS_REORDER_FIELDS = {"productId": PRODUCT_ID, "options": {"type": "array", "minItems": 1, "maxItems": 3, "uniqueItems": True, "items": OPTION_REORDER}}
INVENTORY_ITEM_ID = {"type": "string", "pattern": "^gid://shopify/InventoryItem/[0-9]+$"}
LOCATION_ID = {"type": "string", "pattern": "^gid://shopify/Location/[0-9]+$"}
WEIGHT_INPUT = {
    "type": "object", "additionalProperties": False, "required": ["value", "unit"],
    "properties": {
        "value": {"type": "number", "exclusiveMinimum": 0, "maximum": 1000000},
        "unit": {"type": "string", "enum": ["GRAMS", "KILOGRAMS", "OUNCES", "POUNDS"]},
    },
}
INVENTORY_ITEM_WEIGHT_FIELDS = {"inventoryItemId": INVENTORY_ITEM_ID, "weight": WEIGHT_INPUT}
INVENTORY_CHANGE = {"type": "object", "additionalProperties": False, "required": ["inventoryItemId", "locationId", "delta", "changeFromQuantity"], "properties": {
    "inventoryItemId": INVENTORY_ITEM_ID, "locationId": LOCATION_ID,
    "delta": {"type": "integer", "minimum": -1000000000, "maximum": 1000000000, "not": {"const": 0}},
    "changeFromQuantity": {"type": "integer", "minimum": 0, "maximum": 1000000000},
}}
INVENTORY_ADJUST_FIELDS = {
    "name": {"type": "string", "enum": ["available"]},
    "reason": {"type": "string", "minLength": 1, "maxLength": 255},
    "referenceDocumentUri": {"type": "string", "format": "uri", "minLength": 3, "maxLength": 2048},
    "changes": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": INVENTORY_CHANGE},
}
INVENTORY_TOGGLE_FIELDS = {
    "inventoryItemId": INVENTORY_ITEM_ID,
    "updates": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": {
        "type": "object", "additionalProperties": False, "required": ["locationId", "activate"],
        "properties": {"locationId": LOCATION_ID, "activate": {"type": "boolean"}},
    }},
}
COLLECTION_ID = {"type": "string", "pattern": "^gid://shopify/Collection/[0-9]+$"}
COLLECTION_BASE_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 255},
    "descriptionHtml": {"type": "string", "maxLength": 1000000},
    "handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255},
    "seo": SEO_INPUT,
    "sortOrder": {"type": "string", "enum": ["ALPHA_ASC", "ALPHA_DESC", "BEST_SELLING", "CREATED", "CREATED_DESC", "MANUAL", "PRICE_ASC", "PRICE_DESC"]},
    "templateSuffix": {"type": ["string", "null"], "maxLength": 255},
}
ORDER_ID = {"type": "string", "pattern": "^gid://shopify/Order/[0-9]+$"}
ORDER_UPDATE_FIELDS = {
    "id": ORDER_ID,
    "note": {"type": ["string", "null"], "maxLength": 50000},
    "poNumber": {"type": ["string", "null"], "maxLength": 255},
    "tags": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 255}},
    "customAttributes": {"type": "array", "maxItems": 100, "uniqueItems": True, "items": {"type": "object", "additionalProperties": False, "required": ["key", "value"], "properties": {"key": {"type": "string", "minLength": 1, "maxLength": 255}, "value": {"type": "string", "maxLength": 10000}}}},
}
FULFILLMENT_TRACKING = {"type": "object", "additionalProperties": False, "required": ["numbers"], "properties": {
    "company": {"type": "string", "minLength": 1, "maxLength": 255},
    "numbers": {"type": "array", "minItems": 1, "maxItems": 20, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 255}},
    "urls": {"type": "array", "minItems": 1, "maxItems": 20, "uniqueItems": True, "items": {"type": "string", "pattern": "^https://[^\\s]+$", "maxLength": 2048}},
}}
FULFILLMENT_GROUP = {"type": "object", "additionalProperties": False, "required": ["fulfillmentOrderId", "lineItems"], "properties": {
    "fulfillmentOrderId": {"type": "string", "pattern": "^gid://shopify/FulfillmentOrder/[0-9]+$"},
    "lineItems": {"type": "array", "minItems": 1, "maxItems": 512, "uniqueItems": True, "items": {"type": "object", "additionalProperties": False, "required": ["id", "quantity"], "properties": {"id": {"type": "string", "pattern": "^gid://shopify/FulfillmentOrderLineItem/[0-9]+$"}, "quantity": {"type": "integer", "minimum": 1, "maximum": 1000000}}}},
}}
FULFILLMENT_CREATE_FIELDS = {
    "groups": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": FULFILLMENT_GROUP},
    "notifyCustomer": {"type": "boolean"}, "tracking": FULFILLMENT_TRACKING,
    "message": {"type": "string", "maxLength": 1000},
}
ORDER_CANCEL_FIELDS = {
    "orderId": ORDER_ID,
    "reason": {"type": "string", "enum": ["CUSTOMER", "DECLINED", "FRAUD", "INVENTORY", "OTHER", "STAFF"]},
    "refundOriginalPaymentMethods": {"type": "boolean"},
    "restock": {"type": "boolean"}, "notifyCustomer": {"type": "boolean"},
    "staffNote": {"type": "string", "minLength": 1, "maxLength": 255},
}
REFUND_LINE_ITEM = {"type": "object", "additionalProperties": False, "required": ["lineItemId", "quantity", "restockType"], "properties": {
    "lineItemId": {"type": "string", "pattern": "^gid://shopify/LineItem/[0-9]+$"},
    "quantity": {"type": "integer", "minimum": 1, "maximum": 1000000},
    "restockType": {"type": "string", "enum": ["NO_RESTOCK", "CANCEL", "RETURN"]},
    "locationId": LOCATION_ID,
}, "allOf": [
    {"if": {"properties": {"restockType": {"enum": ["CANCEL", "RETURN"]}}, "required": ["restockType"]}, "then": {"required": ["locationId"]}},
    {"if": {"properties": {"restockType": {"const": "NO_RESTOCK"}}, "required": ["restockType"]}, "then": {"not": {"required": ["locationId"]}}},
]}
REFUND_CREATE_FIELDS = {
    "orderId": ORDER_ID,
    "lineItems": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": REFUND_LINE_ITEM},
    "notifyCustomer": {"type": "boolean"},
    "note": {"type": "string", "minLength": 1, "maxLength": 50000},
}
REFUND_TRANSACTION = {"type": "object", "additionalProperties": False, "required": ["orderId", "kind", "gateway", "amount"], "properties": {
    "orderId": ORDER_ID, "kind": {"type": "string", "enum": ["REFUND"]},
    "gateway": {"type": "string", "minLength": 1, "maxLength": 255}, "amount": {"type": "string", "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]{1,4})?$"},
    "parentId": {"type": "string", "pattern": "^gid://shopify/OrderTransaction/[0-9]+$"},
}}
RETURN_ITEM = {"type": "object", "additionalProperties": False, "required": ["fulfillmentLineItemId", "quantity", "returnReasonDefinitionId"], "properties": {
    "fulfillmentLineItemId": {"type": "string", "pattern": "^gid://shopify/FulfillmentLineItem/[0-9]+$"},
    "quantity": {"type": "integer", "minimum": 1, "maximum": 1000000},
    "returnReasonDefinitionId": {"type": "string", "pattern": "^gid://shopify/ReturnReasonDefinition/[0-9]+$"},
    "returnReasonNote": {"type": "string", "maxLength": 255},
}}
RETURN_CREATE_FIELDS = {"orderId": ORDER_ID, "returnLineItems": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": RETURN_ITEM}, "requestedAt": {"type": "string", "format": "date-time"}}
DRAFT_ORDER_ID = {"type": "string", "pattern": "^gid://shopify/DraftOrder/[0-9]+$"}
DRAFT_LINE_ITEM = {"type": "object", "additionalProperties": False, "required": ["variantId", "quantity"], "properties": {
    "variantId": {"type": "string", "pattern": "^gid://shopify/ProductVariant/[0-9]+$"},
    "quantity": {"type": "integer", "minimum": 1, "maximum": 1000000},
}}
DRAFT_ORDER_FIELDS = {
    "lineItems": {"type": "array", "minItems": 1, "maxItems": 250, "uniqueItems": True, "items": DRAFT_LINE_ITEM},
    "customerId": {"type": "string", "pattern": "^gid://shopify/Customer/[0-9]+$"},
    "email": {"type": "string", "format": "email", "maxLength": 320},
    "note": {"type": ["string", "null"], "maxLength": 50000},
    "tags": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 255}},
    "taxExempt": {"type": "boolean"}, "useCustomerDefaultAddress": {"type": "boolean"},
    "acceptAutomaticDiscounts": {"type": "boolean"},
    "discountCodes": {"type": "array", "maxItems": 5, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 255}},
}
EMAIL_INPUT = {"type": "object", "additionalProperties": False, "minProperties": 1, "properties": {
    "to": {"type": "string", "format": "email", "maxLength": 320},
    "from": {"type": "string", "maxLength": 320},
    "subject": {"type": "string", "maxLength": 998},
    "customMessage": {"type": "string", "maxLength": 50000},
    "bcc": {"type": "array", "maxItems": 20, "uniqueItems": True, "items": {"type": "string", "format": "email", "maxLength": 320}},
}}
DISCOUNT_COMBINES = {"type": "object", "additionalProperties": False, "required": ["orderDiscounts", "productDiscounts", "shippingDiscounts"], "properties": {
    "orderDiscounts": {"type": "boolean"}, "productDiscounts": {"type": "boolean"}, "shippingDiscounts": {"type": "boolean"},
}}
DISCOUNT_BASIC_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 255},
    "code": {"type": "string", "minLength": 1, "maxLength": 255, "pattern": "^[^\\s]+$"},
    "startsAt": {"type": "string", "format": "date-time"}, "endsAt": {"type": ["string", "null"], "format": "date-time"},
    "valueType": {"type": "string", "enum": ["PERCENTAGE", "FIXED_AMOUNT"]},
    "percentage": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
    "fixedAmount": {"type": "string", "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]{1,2})?$"},
    "appliesOnEachItem": {"type": "boolean"},
    "targetType": {"type": "string", "enum": ["ALL", "PRODUCTS", "COLLECTIONS"]},
    "productIds": {"type": "array", "minItems": 1, "maxItems": 250, "uniqueItems": True, "items": PRODUCT_ID},
    "collectionIds": {"type": "array", "minItems": 1, "maxItems": 250, "uniqueItems": True, "items": COLLECTION_ID},
    "audienceType": {"type": "string", "enum": ["ALL", "CUSTOMERS", "SEGMENTS"]},
    "customerIds": {"type": "array", "minItems": 1, "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "pattern": "^gid://shopify/Customer/[0-9]+$"}},
    "segmentIds": {"type": "array", "minItems": 1, "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "pattern": "^gid://shopify/Segment/[0-9]+$"}},
    "minimumType": {"type": "string", "enum": ["NONE", "SUBTOTAL", "QUANTITY"]},
    "minimumSubtotal": {"type": "string", "pattern": "^(0|[1-9][0-9]*)(\\.[0-9]{1,2})?$"},
    "minimumQuantity": {"type": "integer", "minimum": 1, "maximum": 1000000},
    "usageLimit": {"type": ["integer", "null"], "minimum": 1, "maximum": 1000000000},
    "appliesOncePerCustomer": {"type": "boolean"}, "combinesWith": DISCOUNT_COMBINES,
}
DISCOUNT_BASIC_REQUIRED = ["title", "code", "startsAt", "valueType", "targetType", "audienceType", "minimumType", "appliesOncePerCustomer", "combinesWith"]
PAGE_ID = {"type": "string", "pattern": "^gid://shopify/Page/[0-9]+$"}
PAGE_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 255},
    "handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255},
    "body": {"type": "string", "maxLength": 1000000},
    "isPublished": {"type": "boolean"}, "publishDate": {"type": ["string", "null"], "format": "date-time"},
    "templateSuffix": {"type": ["string", "null"], "maxLength": 255},
}
URL_REDIRECT_ID = {"type": "string", "pattern": "^gid://shopify/UrlRedirect/[0-9]+$"}
URL_REDIRECT_FIELDS = {
    "path": {"type": "string", "pattern": "^/[^\\s]*$", "maxLength": 2048},
    "target": {"type": "string", "pattern": "^(?:/[^\\s]*|https://[^\\s]+)$", "maxLength": 2048},
}
MENU_ID = {"type": "string", "pattern": "^gid://shopify/Menu/[0-9]+$"}
MENU_TYPES = ["ARTICLE", "BLOG", "CATALOG", "COLLECTION", "COLLECTIONS", "CUSTOMER_ACCOUNT_PAGE", "FRONTPAGE", "HTTP", "METAOBJECT", "PAGE", "PRODUCT", "SEARCH", "SHOP_POLICY"]


def _menu_item_schema(depth: int, *, update: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "title": {"type": "string", "minLength": 1, "maxLength": 255},
        "type": {"type": "string", "enum": MENU_TYPES},
        "url": {"type": "string", "pattern": "^(?:/[^\\s]*|https://[^\\s]+)$", "maxLength": 2048},
        "resourceId": {"type": "string", "pattern": "^gid://shopify/[A-Za-z][A-Za-z0-9]*/[^/]+$"},
        "tags": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 255}},
    }
    if update:
        properties["id"] = {"type": "string", "pattern": "^gid://shopify/MenuItem/[0-9]+$"}
    properties["items"] = {"type": "array", "maxItems": 50, "items": _menu_item_schema(depth - 1, update=update)} if depth > 1 else {"type": "array", "maxItems": 0}
    return {"type": "object", "additionalProperties": False, "required": ["title", "type", "url", "items"], "properties": properties}


MENU_CREATE_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 255},
    "handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255},
    "items": {"type": "array", "maxItems": 50, "items": _menu_item_schema(3, update=False)},
}
BLOG_ID = {"type": "string", "pattern": "^gid://shopify/Blog/[0-9]+$"}
ARTICLE_ID = {"type": "string", "pattern": "^gid://shopify/Article/[0-9]+$"}
BLOG_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 255},
    "handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255},
    "templateSuffix": {"type": ["string", "null"], "maxLength": 255},
    "commentPolicy": {"type": "string", "enum": ["AUTO_PUBLISHED", "CLOSED", "MODERATED"]},
}
ARTICLE_IMAGE = {"type": ["object", "null"], "additionalProperties": False, "required": ["url"], "properties": {
    "url": {"type": "string", "pattern": "^https://[^\\s]+$", "maxLength": 2048}, "altText": {"type": "string", "maxLength": 512},
}}
ARTICLE_FIELDS = {
    "blogId": BLOG_ID, "title": {"type": "string", "minLength": 1, "maxLength": 255},
    "authorName": {"type": "string", "minLength": 1, "maxLength": 255},
    "handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255},
    "body": {"type": "string", "maxLength": 2000000}, "summary": {"type": "string", "maxLength": 100000},
    "isPublished": {"type": "boolean"}, "publishDate": {"type": ["string", "null"], "format": "date-time"},
    "tags": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "minLength": 1, "maxLength": 255}},
    "templateSuffix": {"type": ["string", "null"], "maxLength": 255}, "image": ARTICLE_IMAGE,
}
METAFIELD_OWNER_ID = {"type": "string", "pattern": "^gid://shopify/[A-Za-z][A-Za-z0-9]*/[^/]+$"}
METAFIELD_NAMESPACE = {"type": "string", "pattern": "^[A-Za-z0-9_$][A-Za-z0-9_.$:-]{0,254}$"}
METAFIELD_KEY = {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"}
METAFIELD_SET_ITEM = {
    "type": "object", "additionalProperties": False,
    "required": ["ownerId", "namespace", "key", "type", "value", "compareDigest"],
    "properties": {
        "ownerId": METAFIELD_OWNER_ID, "namespace": METAFIELD_NAMESPACE, "key": METAFIELD_KEY,
        "type": {"type": "string", "minLength": 1, "maxLength": 255},
        "value": {"type": "string", "maxLength": 5000000},
        "compareDigest": {"type": ["string", "null"], "minLength": 1, "maxLength": 255},
    },
}
METAFIELD_DELETE_ITEM = {
    "type": "object", "additionalProperties": False,
    "required": ["ownerId", "namespace", "key", "compareDigest"],
    "properties": {
        "ownerId": METAFIELD_OWNER_ID, "namespace": METAFIELD_NAMESPACE, "key": METAFIELD_KEY,
        "compareDigest": {"type": "string", "minLength": 1, "maxLength": 255},
    },
}
METAFIELD_SET_FIELDS = {"metafields": {"type": "array", "minItems": 1, "maxItems": 25, "items": METAFIELD_SET_ITEM}}
METAFIELD_DELETE_FIELDS = {"metafields": {"type": "array", "minItems": 1, "maxItems": 25, "items": METAFIELD_DELETE_ITEM}}
METAFIELD_OWNER_TYPES = ["API_PERMISSION", "ARTICLE", "BLOG", "CARTTRANSFORM", "COLLECTION", "COMPANY", "COMPANY_LOCATION", "CUSTOMER", "DELIVERY_CUSTOMIZATION", "DISCOUNT", "DRAFTORDER", "FULFILLMENT_CONSTRAINT_RULE", "GIFT_CARD_TRANSACTION", "LOCATION", "MARKET", "ORDER", "ORDER_ROUTING_LOCATION_RULE", "PAGE", "PAYMENT_CUSTOMIZATION", "PRODUCT", "PRODUCTVARIANT", "SELLING_PLAN", "SHOP", "TRANSFER", "VALIDATION"]
METAFIELD_DEFINITION_ID = {"type": "string", "pattern": "^gid://shopify/MetafieldDefinition/[0-9]+$"}
METAFIELD_VALIDATIONS = {"type": "array", "maxItems": 25, "items": {"type": "object", "additionalProperties": False, "required": ["name", "value"], "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 255}, "value": {"type": "string", "maxLength": 5000}}}}
METAFIELD_DEFINITION_IDENTIFIER = {"namespace": METAFIELD_NAMESPACE, "key": METAFIELD_KEY, "ownerType": {"type": "string", "enum": METAFIELD_OWNER_TYPES}}
METAFIELD_DEFINITION_CREATE_FIELDS = {
    "name": {"type": "string", "minLength": 1, "maxLength": 255}, **METAFIELD_DEFINITION_IDENTIFIER,
    "description": {"type": "string", "maxLength": 5000}, "type": {"type": "string", "minLength": 1, "maxLength": 255},
    "pin": {"type": "boolean"}, "validations": METAFIELD_VALIDATIONS,
}
METAFIELD_DEFINITION_UPDATE_FIELDS = {**METAFIELD_DEFINITION_IDENTIFIER, "name": METAFIELD_DEFINITION_CREATE_FIELDS["name"], "description": {"type": ["string", "null"], "maxLength": 5000}, "validations": METAFIELD_VALIDATIONS}
METAOBJECT_ID = {"type": "string", "pattern": "^gid://shopify/Metaobject/[0-9]+$"}
METAOBJECT_DEFINITION_ID = {"type": "string", "pattern": "^gid://shopify/MetaobjectDefinition/[0-9]+$"}
METAOBJECT_TYPE = {"type": "string", "pattern": "^(?:\\$app:)?[A-Za-z0-9][A-Za-z0-9_-]{2,254}$"}
METAOBJECT_HANDLE = {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255}
METAOBJECT_FIELD_VALUE = {"type": "object", "additionalProperties": False, "required": ["key", "value"], "properties": {"key": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$"}, "value": {"type": ["string", "null"], "maxLength": 5000000}}}
METAOBJECT_CAPABILITY_DATA = {"type": "object", "additionalProperties": False, "properties": {"publishable": {"type": "object", "additionalProperties": False, "required": ["status"], "properties": {"status": {"type": "string", "enum": ["ACTIVE", "DRAFT"]}}}}}
METAOBJECT_CREATE_FIELDS = {"type": METAOBJECT_TYPE, "handle": METAOBJECT_HANDLE, "fields": {"type": "array", "maxItems": 100, "uniqueItems": True, "items": METAOBJECT_FIELD_VALUE}, "capabilities": METAOBJECT_CAPABILITY_DATA}
METAOBJECT_UPDATE_FIELDS = {"id": METAOBJECT_ID, "handle": METAOBJECT_HANDLE, "redirectNewHandle": {"type": "boolean"}, "fields": METAOBJECT_CREATE_FIELDS["fields"], "capabilities": METAOBJECT_CAPABILITY_DATA}
METAOBJECT_ACCESS = {"type": "object", "additionalProperties": False, "properties": {"admin": {"type": "string", "enum": ["MERCHANT_READ", "MERCHANT_READ_WRITE"]}, "storefront": {"type": "string", "enum": ["NONE", "PUBLIC_READ"]}, "customerAccount": {"type": "string", "enum": ["NONE", "READ"]}}}
METAOBJECT_FIELD_DEFINITION = {"type": "object", "additionalProperties": False, "required": ["key", "name", "type", "required"], "properties": {"key": METAOBJECT_FIELD_VALUE["properties"]["key"], "name": {"type": "string", "minLength": 1, "maxLength": 255}, "description": {"type": "string", "maxLength": 5000}, "type": {"type": "string", "minLength": 1, "maxLength": 255}, "required": {"type": "boolean"}, "validations": METAFIELD_VALIDATIONS}}
METAOBJECT_DEFINITION_CREATE_FIELDS = {"name": {"type": "string", "minLength": 1, "maxLength": 255}, "type": METAOBJECT_TYPE, "description": {"type": "string", "maxLength": 5000}, "displayNameKey": METAOBJECT_FIELD_VALUE["properties"]["key"], "access": METAOBJECT_ACCESS, "fieldDefinitions": {"type": "array", "minItems": 1, "maxItems": 100, "items": METAOBJECT_FIELD_DEFINITION}}
METAOBJECT_FIELD_UPDATE = {"type": "object", "additionalProperties": False, "required": ["key"], "properties": {"key": METAOBJECT_FIELD_VALUE["properties"]["key"], "name": METAOBJECT_FIELD_DEFINITION["properties"]["name"], "description": {"type": ["string", "null"], "maxLength": 5000}, "required": {"type": "boolean"}, "validations": METAFIELD_VALIDATIONS}}
METAOBJECT_FIELD_OPERATION = {"type": "object", "additionalProperties": False, "oneOf": [{"required": ["create"]}, {"required": ["update"]}, {"required": ["delete"]}], "properties": {"create": METAOBJECT_FIELD_DEFINITION, "update": METAOBJECT_FIELD_UPDATE, "delete": {"type": "object", "additionalProperties": False, "required": ["key"], "properties": {"key": METAOBJECT_FIELD_VALUE["properties"]["key"]}}}}
METAOBJECT_DEFINITION_UPDATE_FIELDS = {"id": METAOBJECT_DEFINITION_ID, "name": {"type": "string", "minLength": 1, "maxLength": 255}, "description": {"type": ["string", "null"], "maxLength": 5000}, "displayNameKey": {**METAOBJECT_FIELD_VALUE["properties"]["key"], "type": ["string", "null"]}, "access": METAOBJECT_ACCESS, "fieldDefinitions": {"type": "array", "maxItems": 100, "items": METAOBJECT_FIELD_OPERATION}, "resetFieldOrder": {"type": "boolean"}, "acknowledgeFieldDataLoss": {"type": "boolean"}}
FILE_ID = {"type": "string", "pattern": "^gid://shopify/(?:GenericFile|MediaImage|Video|ExternalVideo|Model3d)/[0-9]+$"}
HTTPS_URL = {"type": "string", "pattern": "^https://[^\\s]+$", "maxLength": 4096}
FILE_CREATE_ITEM = {"type": "object", "additionalProperties": False, "required": ["originalSource", "duplicateResolutionMode"], "properties": {"originalSource": HTTPS_URL, "alt": {"type": ["string", "null"], "maxLength": 512}, "contentType": {"type": "string", "enum": ["IMAGE", "VIDEO", "MODEL_3D", "EXTERNAL_VIDEO", "GENERIC_FILE"]}, "duplicateResolutionMode": {"type": "string", "enum": ["APPEND_UUID", "REPLACE", "RAISE_ERROR"]}, "filename": {"type": "string", "pattern": "^[^/\\\\]+$", "maxLength": 255}}}
FILE_CREATE_FIELDS = {"files": {"type": "array", "minItems": 1, "maxItems": 25, "items": FILE_CREATE_ITEM}}
PRODUCT_IDS = {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"}}
FILE_UPDATE_ITEM = {"type": "object", "additionalProperties": False, "required": ["id"], "properties": {"id": FILE_ID, "alt": {"type": ["string", "null"], "maxLength": 512}, "filename": FILE_CREATE_ITEM["properties"]["filename"], "originalSource": HTTPS_URL, "previewImageSource": HTTPS_URL, "referencesToAdd": PRODUCT_IDS, "referencesToRemove": PRODUCT_IDS}}
FILE_UPDATE_FIELDS = {"files": {"type": "array", "minItems": 1, "maxItems": 25, "items": FILE_UPDATE_ITEM}}
FILE_DELETE_FIELDS = {"fileIds": {"type": "array", "minItems": 1, "maxItems": 25, "uniqueItems": True, "items": FILE_ID}, "confirmRemoveReferences": {"type": "boolean"}}
STAGED_UPLOAD_ITEM = {"type": "object", "additionalProperties": False, "required": ["filename", "mimeType", "resource", "httpMethod"], "properties": {"filename": FILE_CREATE_ITEM["properties"]["filename"], "mimeType": {"type": "string", "pattern": "^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$", "maxLength": 255}, "fileSize": {"type": "string", "pattern": "^[1-9][0-9]*$", "maxLength": 20}, "httpMethod": {"type": "string", "enum": ["POST", "PUT"]}, "resource": {"type": "string", "enum": ["COLLECTION_IMAGE", "FILE", "IMAGE", "MODEL_3D", "SHOP_IMAGE", "VIDEO"]}}}
STAGED_UPLOAD_FIELDS = {"input": {"type": "array", "minItems": 1, "maxItems": 25, "items": STAGED_UPLOAD_ITEM}}
PUBLISHABLE_ID = {"type": "string", "pattern": "^gid://shopify/(?:Product|Collection)/[0-9]+$"}
PUBLICATION_INPUT = {"type": "object", "additionalProperties": False, "required": ["publicationId"], "properties": {"publicationId": {"type": "string", "pattern": "^gid://shopify/Publication/-?[0-9]+$"}, "publishDate": {"type": "string", "format": "date-time"}}}
PUBLISH_FIELDS = {"id": PUBLISHABLE_ID, "publications": {"type": "array", "minItems": 1, "maxItems": 25, "items": PUBLICATION_INPUT}}
UNPUBLISH_FIELDS = {"id": PUBLISHABLE_ID, "publicationIds": {"type": "array", "minItems": 1, "maxItems": 25, "uniqueItems": True, "items": PUBLICATION_INPUT["properties"]["publicationId"]}}
MARKET_ID = {"type": "string", "pattern": "^gid://shopify/Market/[0-9]+$"}
CATALOG_IDS = {"type": "array", "maxItems": 100, "uniqueItems": True, "items": {"type": "string", "pattern": "^gid://shopify/(?:MarketCatalog|CompanyLocationCatalog|AppCatalog|Catalog)/[0-9]+$"}}
MARKET_REGIONS = {"type": "array", "minItems": 1, "maxItems": 250, "items": {"type": "object", "additionalProperties": False, "required": ["countryCode"], "properties": {"countryCode": {"type": "string", "pattern": "^[A-Z]{2}$"}}}}
MARKET_CONDITIONS = {"type": "object", "additionalProperties": False, "required": ["regionsCondition"], "properties": {"regionsCondition": {"type": "object", "additionalProperties": False, "required": ["regions"], "properties": {"regions": MARKET_REGIONS}}}}
MARKET_CURRENCY = {"type": "object", "additionalProperties": False, "required": ["baseCurrency", "localCurrencies"], "properties": {"baseCurrency": {"type": "string", "pattern": "^[A-Z]{3}$"}, "localCurrencies": {"type": "boolean"}}}
MARKET_CREATE_FIELDS = {"name": {"type": "string", "minLength": 1, "maxLength": 255}, "handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255}, "status": {"type": "string", "enum": ["ACTIVE", "DRAFT"]}, "conditions": MARKET_CONDITIONS, "currencySettings": MARKET_CURRENCY, "catalogs": CATALOG_IDS, "makeDuplicateUniqueMarketsDraft": {"type": "boolean"}}
MARKET_UPDATE_FIELDS = {"id": MARKET_ID, "name": MARKET_CREATE_FIELDS["name"], "handle": MARKET_CREATE_FIELDS["handle"], "status": MARKET_CREATE_FIELDS["status"], "conditions": MARKET_CONDITIONS, "currencySettings": MARKET_CURRENCY, "removeCurrencySettings": {"type": "boolean"}, "catalogsToAdd": CATALOG_IDS, "catalogsToDelete": CATALOG_IDS, "makeDuplicateUniqueMarketsDraft": {"type": "boolean"}}
CATALOG_ID = {"type": "string", "pattern": "^gid://shopify/(?:MarketCatalog|CompanyLocationCatalog|AppCatalog|Catalog)/[0-9]+$"}
PRICE_LIST_ID = {"type": "string", "pattern": "^gid://shopify/PriceList/[0-9]+$"}
MONEY_INPUT = {"type": "object", "additionalProperties": False, "required": ["amount", "currencyCode"], "properties": {"amount": {"type": "string", "pattern": "^(0|[1-9][0-9]*)(?:\\.[0-9]{1,2})?$"}, "currencyCode": {"type": "string", "pattern": "^[A-Z]{3}$"}}}
FIXED_PRICE_ITEM = {"type": "object", "additionalProperties": False, "required": ["variantId", "price"], "properties": {"variantId": {"type": "string", "pattern": "^gid://shopify/ProductVariant/[0-9]+$"}, "price": MONEY_INPUT, "compareAtPrice": {"anyOf": [MONEY_INPUT, {"type": "null"}]}}}
FIXED_PRICES_ADD_FIELDS = {"priceListId": PRICE_LIST_ID, "prices": {"type": "array", "minItems": 1, "maxItems": 100, "items": FIXED_PRICE_ITEM}}
FIXED_PRICES_DELETE_FIELDS = {"priceListId": PRICE_LIST_ID, "variantIds": {"type": "array", "minItems": 1, "maxItems": 100, "uniqueItems": True, "items": FIXED_PRICE_ITEM["properties"]["variantId"]}}
WEBHOOK_ID = {"type": "string", "pattern": "^gid://shopify/WebhookSubscription/[0-9]+$"}
WEBHOOK_URI = {"type": "string", "pattern": "^(?:https://[^\\s]+|pubsub://[A-Za-z0-9._-]+:[A-Za-z0-9._-]+|arn:aws:events:[A-Za-z0-9-]+:[0-9]{12}:event-source/[A-Za-z0-9._/-]+)$", "maxLength": 4096}
WEBHOOK_INPUT_FIELDS = {"uri": WEBHOOK_URI, "format": {"type": "string", "enum": ["JSON", "XML"]}, "filter": {"type": ["string", "null"], "maxLength": 2000}, "includeFields": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": {"type": "string", "pattern": "^[A-Za-z0-9_.]+$", "maxLength": 255}}, "metafieldNamespaces": {"type": "array", "maxItems": 250, "uniqueItems": True, "items": METAFIELD_NAMESPACE}, "name": {"type": ["string", "null"], "maxLength": 255}}
WEBHOOK_CREATE_FIELDS = {"topic": {"type": "string", "pattern": "^[A-Z][A-Z0-9_]+$", "maxLength": 255}, **WEBHOOK_INPUT_FIELDS}
WEBHOOK_UPDATE_FIELDS = {"id": WEBHOOK_ID, **WEBHOOK_INPUT_FIELDS}
BULK_OPERATION_ID = {"type": "string", "pattern": "^gid://shopify/BulkOperation/[0-9]+$"}
BULK_EXPORT_FIELDS = {
    "resource": {"type": "string", "enum": ["PRODUCTS", "PRODUCT_VARIANTS", "COLLECTIONS", "ORDERS", "CUSTOMERS", "INVENTORY_ITEMS", "METAOBJECTS"]},
    "query": {"type": "string", "maxLength": 1000, "description": "Filtro Shopify opcional; nunca é interpretado como GraphQL."},
    "metaobjectType": METAOBJECT_TYPE,
    "groupObjects": {"type": "boolean", "default": False, "description": "Agrupa filhos no JSONL; é mais lento e deve permanecer false salvo necessidade comprovada."},
}
BULK_IMPORT_KIND = {"type": "string", "enum": ["PRODUCT_CREATE", "PRODUCT_UPDATE", "PRODUCT_VARIANTS_BULK_UPDATE", "METAFIELDS_SET", "METAOBJECT_CREATE", "METAOBJECT_UPDATE"]}
BULK_IMPORT_STAGE_FIELDS = {
    "filename": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*\\.jsonl$", "maxLength": 255},
    "fileSize": {"type": "string", "pattern": "^[1-9][0-9]*$", "maxLength": 20},
}
BULK_IMPORT_FIELDS = {
    "kind": BULK_IMPORT_KIND,
    "stagedUploadPath": {"type": "string", "pattern": "^tmp/[A-Za-z0-9._/-]+$", "maxLength": 2048},
    "clientIdentifier": {"type": "string", "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]*$", "maxLength": 255},
    "lineCount": {"type": "integer", "minimum": 1, "maximum": 10000000},
    "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
    "acknowledgeUnorderedExecution": {"type": "boolean", "const": True},
}


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    tool: types.Tool
    route: str
    domain: str
    write: bool = False
    profiles: frozenset[str] = frozenset({"readonly", "catalog", "orders", "full"})


def _tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None, *, write: bool = False, destructive: bool = False) -> types.Tool:
    return types.Tool(
        name=name,
        description=description,
        inputSchema={"type": "object", "properties": properties, "required": required or [], "additionalProperties": False},
        annotations=DESTRUCTIVE_WRITE if destructive else (WRITE if write else READ),
    )


DEFINITIONS = [
    ToolDefinition(_tool("shopify_get_shop", "Valida a conexão e retorna contexto básico da loja e versão da API.", {}), "get_shop", "shop"),
    ToolDefinition(_tool("shopify_get_access_scopes", "Lista os scopes realmente concedidos ao app. Use antes de diagnosticar erros de permissão ou planejar mutações.", {}), "get_access_scopes", "shop"),
    ToolDefinition(_tool("shopify_list_publications", "Lista publicações/canais que controlam a disponibilidade de produtos e coleções.", PAGE), "list_publications", "publications"),
    ToolDefinition(_tool("shopify_get_publication", "Obtém uma publicação pelo GID.", {"id": {"type": "string", "pattern": "^gid://shopify/Publication/-?[0-9]+$"}}, ["id"]), "get_publication", "publications"),
    ToolDefinition(_tool("shopify_list_product_types", "Lista tipos de produto já usados na loja.", PAGE), "list_product_types", "products"),
    ToolDefinition(_tool("shopify_list_product_vendors", "Lista fornecedores/marcas já usados nos produtos da loja.", PAGE), "list_product_vendors", "products"),
    ToolDefinition(_tool("shopify_list_products", "Lista e pesquisa produtos com variantes, SEO, tags e estoque. Retorna endCursor para paginação.", SEARCH_PAGE), "list_products", "products"),
    ToolDefinition(_tool("shopify_get_product", "Obtém um produto completo pelo GID Shopify.", {"id": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$", "description": "GID do produto."}}, ["id"]), "get_product", "products"),
    ToolDefinition(_tool("shopify_get_product_by_handle", "Obtém produto pelo handle exato.", {"handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255}}, ["handle"]), "get_product_by_handle", "products"),
    ToolDefinition(_tool("shopify_count_products", "Conta produtos que correspondem à sintaxe de busca Shopify.", {"query": {"type": "string", "maxLength": 1000}}), "count_products", "products"),
    ToolDefinition(_tool("shopify_get_product_360", "View composta para integração: produto, opções, variantes, estoque por local, metafields, coleções e publicações em páginas limitadas.", {"id": PRODUCT_ID, "variantFirst": {"type": "integer", "minimum": 1, "maximum": 50, "default": 25}, "variantAfter": {"type": "string"}}, ["id"]), "get_product_360", "composite_views"),
    ToolDefinition(_tool("shopify_audit_product_data", "Audita uma página de produtos e variantes por lacunas de cadastro, SEO, mídia e identificadores; não altera dados.", SEARCH_PAGE), "audit_product_data", "composite_views"),
    ToolDefinition(_tool("shopify_shopifyql_query", "Executa uma consulta ShopifyQL (datasets de analytics, ex.: sales com line_item_is_bundle/bundle_title) e retorna tabela (colunas + linhas) ou erros de parse. Somente leitura; requer scope de relatórios.", {"query": {"type": "string", "minLength": 1, "maxLength": 4000}}, ["query"]), "shopifyql_query", "composite_views"),
    ToolDefinition(_tool("shopify_list_product_variants", "Pesquisa variantes globalmente por SKU, barcode, produto, status e outros filtros Shopify.", SEARCH_PAGE), "list_product_variants", "variants"),
    ToolDefinition(_tool("shopify_get_product_variant", "Obtém uma variante pelo GID.", {"id": {"type": "string", "pattern": "^gid://shopify/ProductVariant/[0-9]+$"}}, ["id"]), "get_product_variant", "variants"),
    ToolDefinition(_tool("shopify_get_product_variant_by_sku", "Obtém uma variante por SKU exato. Retorna null quando não encontrada.", {"sku": {"type": "string", "minLength": 1, "maxLength": 255}}, ["sku"]), "get_product_variant_by_sku", "variants"),
    ToolDefinition(_tool("shopify_prepare_product_create", "Prepara criação de produto em estado não publicado e retorna token de uso único.", PRODUCT_CREATE_FIELDS, ["title"]), "prepare_product_create", "products", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_product", "ESCRITA: cria produto previamente preparado. Variantes adicionais e publicação são operações separadas.", {**PRODUCT_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["title", "confirmationToken"], write=True), "create_product", "products", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_product_update", "Consulta estado atual e prepara atualização dos campos básicos de produto.", {"id": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"}, **PRODUCT_UPDATE_FIELDS}, ["id"]), "prepare_product_update", "products", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_product", "ESCRITA: aplica atualização de produto previamente preparada.", {"id": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"}, **PRODUCT_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_product", "products", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_variants_bulk_create", "Prepara criação atômica de até 100 variantes. Exige estratégia explícita para a variante standalone.", VARIANT_CREATE_FIELDS, ["productId", "strategy", "variants"]), "prepare_variants_bulk_create", "variants", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_variants_bulk_create", "ESCRITA: cria variantes previamente preparadas em uma única mutation.", {**VARIANT_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["productId", "strategy", "variants", "confirmationToken"], write=True), "variants_bulk_create", "variants", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_variants_bulk_update", "Valida pertencimento e prepara atualização atômica de até 100 variantes.", VARIANT_UPDATE_FIELDS, ["productId", "variants"]), "prepare_variants_bulk_update", "variants", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_variants_bulk_update", "ESCRITA: atualiza variantes atomicamente; qualquer erro impede todo o lote.", {**VARIANT_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["productId", "variants", "confirmationToken"], write=True), "variants_bulk_update", "variants", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_product_options_create", "Prepara criação de opções e explicita se novas combinações de variantes serão criadas.", OPTIONS_CREATE_FIELDS, ["productId", "options", "variantStrategy"]), "prepare_product_options_create", "options", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_product_options_create", "ESCRITA: cria opções previamente preparadas.", {**OPTIONS_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["productId", "options", "variantStrategy", "confirmationToken"], write=True), "product_options_create", "options", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_product_option_update", "Valida pertencimento e prepara alteração de uma opção e seus valores.", OPTION_UPDATE_FIELDS, ["productId", "optionId", "variantStrategy"]), "prepare_product_option_update", "options", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_product_option_update", "ESCRITA: altera uma opção previamente preparada.", {**OPTION_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["productId", "optionId", "variantStrategy", "confirmationToken"], write=True), "product_option_update", "options", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_product_options_delete", "Prepara exclusão de opções, com estratégia obrigatória e aviso de impacto em variantes.", OPTIONS_DELETE_FIELDS, ["productId", "optionIds", "strategy"]), "prepare_product_options_delete", "options", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_product_options_delete", "ESCRITA: exclui opções previamente preparadas; POSITION pode apagar variantes duplicadas.", {**OPTIONS_DELETE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["productId", "optionIds", "strategy", "confirmationToken"], write=True), "product_options_delete", "options", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_product_options_reorder", "Valida a ordem completa das opções e valores antes de preparar a alteração.", OPTIONS_REORDER_FIELDS, ["productId", "options"]), "prepare_product_options_reorder", "options", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_product_options_reorder", "ESCRITA: reordena opções e valores previamente preparados.", {**OPTIONS_REORDER_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["productId", "options", "confirmationToken"], write=True), "product_options_reorder", "options", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_orders", "Lista pedidos. Por padrão a Shopify limita acesso aos últimos 60 dias sem read_all_orders.", SEARCH_PAGE), "list_orders", "orders"),
    ToolDefinition(_tool("shopify_get_order", "Obtém pedido, itens, cliente, endereço e rastreios pelo GID.", {"id": {"type": "string", "pattern": "^gid://shopify/Order/[0-9]+$"}}, ["id"]), "get_order", "orders"),
    ToolDefinition(_tool("shopify_count_orders", "Conta pedidos por filtros Shopify e informa a precisão.", {"query": {"type": "string", "maxLength": 1000}, "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 1000000}}, []), "count_orders", "orders"),
    ToolDefinition(_tool("shopify_get_order_financials", "Obtém transações, riscos, reembolsos e devoluções financeiras de um pedido.", {"id": {"type": "string", "pattern": "^gid://shopify/Order/[0-9]+$"}}, ["id"]), "get_order_financials", "orders"),
    ToolDefinition(_tool("shopify_get_order_360", "View composta para integração: pedido, financeiro, riscos, refunds, returns e fulfillment orders.", {"id": ORDER_ID}, ["id"]), "get_order_360", "composite_views"),
    ToolDefinition(_tool("shopify_list_order_fulfillment_orders", "Lista fulfillment orders e itens elegíveis para atendimento de um pedido.", {"id": {"type": "string", "pattern": "^gid://shopify/Order/[0-9]+$"}, **PAGE}, ["id"]), "list_order_fulfillment_orders", "fulfillment"),
    ToolDefinition(_tool("shopify_prepare_order_update", "Prepara atualização administrativa de nota, PO, tags ou atributos; listas substituem integralmente os valores atuais.", ORDER_UPDATE_FIELDS, ["id"]), "prepare_order_update", "orders", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_update_order", "ESCRITA: aplica atualização administrativa do pedido previamente preparada.", {**ORDER_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_order", "orders", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_fulfillment_create", "Valida pedido, local, status e quantidades e prepara atendimento explícito de itens.", FULFILLMENT_CREATE_FIELDS, ["groups", "notifyCustomer"]), "prepare_fulfillment_create", "fulfillment", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_create_fulfillment", "ESCRITA: cria fulfillment previamente preparado; nunca atende implicitamente todos os itens.", {**FULFILLMENT_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["groups", "notifyCustomer", "confirmationToken"], write=True), "create_fulfillment", "fulfillment", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_fulfillment_tracking_update", "Consulta rastreio atual e prepara substituição; notificação ao cliente deve ser explícita.", {"fulfillmentId": {"type": "string", "pattern": "^gid://shopify/Fulfillment/[0-9]+$"}, "tracking": FULFILLMENT_TRACKING, "notifyCustomer": {"type": "boolean"}}, ["fulfillmentId", "tracking", "notifyCustomer"]), "prepare_fulfillment_tracking_update", "fulfillment", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_update_fulfillment_tracking", "ESCRITA: substitui rastreio do fulfillment conforme preview confirmado.", {"fulfillmentId": {"type": "string", "pattern": "^gid://shopify/Fulfillment/[0-9]+$"}, "tracking": FULFILLMENT_TRACKING, "notifyCustomer": {"type": "boolean"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["fulfillmentId", "tracking", "notifyCustomer", "confirmationToken"], write=True), "update_fulfillment_tracking", "fulfillment", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_order_cancel", "Prepara cancelamento irreversível com política explícita de refund, restock e notificação.", ORDER_CANCEL_FIELDS, ["orderId", "reason", "refundOriginalPaymentMethods", "restock", "notifyCustomer", "staffNote"]), "prepare_order_cancel", "orders", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_cancel_order", "ESCRITA FINANCEIRA E DESTRUTIVA: cancela o pedido conforme preview confirmado.", {**ORDER_CANCEL_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["orderId", "reason", "refundOriginalPaymentMethods", "restock", "notifyCustomer", "staffNote", "confirmationToken"], write=True, destructive=True), "cancel_order", "orders", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_refund_create", "Calcula o refund sugerido pela Shopify e prepara itens, restock e transações financeiras idempotentes.", REFUND_CREATE_FIELDS, ["orderId", "lineItems", "notifyCustomer", "note"]), "prepare_refund_create", "refunds", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_create_refund", "ESCRITA FINANCEIRA: cria refund parcial previamente calculado e confirmado.", {**REFUND_CREATE_FIELDS, "idempotencyKey": {"type": "string", "format": "uuid"}, "transactions": {"type": "array", "maxItems": 20, "items": REFUND_TRANSACTION}, "currency": {"type": "string", "pattern": "^[A-Z]{3}$"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["orderId", "lineItems", "notifyCustomer", "note", "idempotencyKey", "transactions", "currency", "confirmationToken"], write=True, destructive=True), "create_refund", "refunds", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_list_return_reason_definitions", "Lista motivos padronizados atuais para criar devoluções sem usar enum legado.", {**PAGE, "query": {"type": "string", "maxLength": 1000}}), "list_return_reason_definitions", "returns"),
    ToolDefinition(_tool("shopify_list_returnable_fulfillments", "Lista itens entregues que ainda podem ser incluídos em devolução para um pedido.", {"orderId": ORDER_ID, **PAGE}, ["orderId"]), "list_returnable_fulfillments", "returns"),
    ToolDefinition(_tool("shopify_get_return", "Obtém devolução, itens, reverse fulfillment, refunds e transações.", {"id": {"type": "string", "pattern": "^gid://shopify/Return/[0-9]+$"}}, ["id"]), "get_return", "returns"),
    ToolDefinition(_tool("shopify_prepare_return_create", "Valida elegibilidade e motivo padronizado e prepara uma devolução aprovada em estado OPEN.", RETURN_CREATE_FIELDS, ["orderId", "returnLineItems"]), "prepare_return_create", "returns", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_create_return", "ESCRITA: cria devolução formal previamente preparada; refund é operação separada.", {**RETURN_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["orderId", "returnLineItems", "confirmationToken"], write=True), "create_return", "returns", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_list_draft_orders", "Lista e pesquisa pedidos em rascunho, seus totais, status e cliente.", SEARCH_PAGE), "list_draft_orders", "draft_orders"),
    ToolDefinition(_tool("shopify_get_draft_order", "Obtém um draft order com itens, preços, descontos, endereços e invoice.", {"id": DRAFT_ORDER_ID}, ["id"]), "get_draft_order", "draft_orders"),
    ToolDefinition(_tool("shopify_prepare_draft_order_create", "Calcula preços, impostos e descontos na Shopify antes de preparar a criação do draft order.", DRAFT_ORDER_FIELDS, ["lineItems"]), "prepare_draft_order_create", "draft_orders", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_create_draft_order", "ESCRITA: cria o draft order exatamente conforme cálculo e confirmação anteriores.", {**DRAFT_ORDER_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["lineItems", "confirmationToken"], write=True), "create_draft_order", "draft_orders", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_draft_order_invoice_send", "Prepara o envio externo da invoice e mostra destinatário, assunto e total.", {"id": DRAFT_ORDER_ID, "email": EMAIL_INPUT}, ["id"]), "prepare_draft_order_invoice_send", "draft_orders", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_send_draft_order_invoice", "ESCRITA COM EFEITO EXTERNO: envia a invoice previamente confirmada.", {"id": DRAFT_ORDER_ID, "email": EMAIL_INPUT, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "send_draft_order_invoice", "draft_orders", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_draft_order_complete", "Confere status, totais e estoque antes de converter o draft em pedido pago.", {"id": DRAFT_ORDER_ID, "paymentGatewayId": {"type": "string", "pattern": "^gid://shopify/PaymentGateway/[0-9]+$"}, "sourceName": {"type": "string", "minLength": 1, "maxLength": 255}}, ["id"]), "prepare_draft_order_complete", "draft_orders", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_complete_draft_order", "ESCRITA FINANCEIRA E DESTRUTIVA: converte o draft em pedido e reserva estoque.", {"id": DRAFT_ORDER_ID, "paymentGatewayId": {"type": "string", "pattern": "^gid://shopify/PaymentGateway/[0-9]+$"}, "sourceName": {"type": "string", "minLength": 1, "maxLength": 255}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "complete_draft_order", "draft_orders", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_draft_order_delete", "Prepara exclusão irreversível de um draft ainda aberto.", {"id": DRAFT_ORDER_ID}, ["id"]), "prepare_draft_order_delete", "draft_orders", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_delete_draft_order", "ESCRITA DESTRUTIVA: exclui definitivamente o draft previamente confirmado.", {"id": DRAFT_ORDER_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_draft_order", "draft_orders", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_list_code_discounts", "Lista cupons de todos os tipos com tipo concreto, status, vigência, uso e resumo.", SEARCH_PAGE), "list_code_discounts", "discounts"),
    ToolDefinition(_tool("shopify_get_code_discount", "Obtém um cupom pelo DiscountCodeNode GID com seus códigos e configuração principal.", {"id": {"type": "string", "pattern": "^gid://shopify/DiscountCodeNode/[0-9]+$"}}, ["id"]), "get_code_discount", "discounts"),
    ToolDefinition(_tool("shopify_get_code_discount_by_code", "Localiza cupom pelo código sem diferenciar maiúsculas e minúsculas.", {"code": {"type": "string", "minLength": 1, "maxLength": 255}}, ["code"]), "get_code_discount_by_code", "discounts"),
    ToolDefinition(_tool("shopify_prepare_discount_code_basic_create", "Valida código, GIDs, vigência, público, alvo e valor antes de criar cupom de desconto básico.", DISCOUNT_BASIC_FIELDS, DISCOUNT_BASIC_REQUIRED), "prepare_discount_code_basic_create", "discounts", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_create_discount_code_basic", "ESCRITA: cria cupom de percentual ou valor fixo previamente validado e confirmado.", {**DISCOUNT_BASIC_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, [*DISCOUNT_BASIC_REQUIRED, "confirmationToken"], write=True), "create_discount_code_basic", "discounts", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_discount_code_status_change", "Mostra alterações de vigência que a Shopify pode fazer ao ativar ou desativar um cupom.", {"id": {"type": "string", "pattern": "^gid://shopify/DiscountCodeNode/[0-9]+$"}, "action": {"type": "string", "enum": ["ACTIVATE", "DEACTIVATE"]}}, ["id", "action"]), "prepare_discount_code_status_change", "discounts", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_set_discount_code_status", "ESCRITA: ativa ou desativa cupom conforme confirmação; a Shopify pode ajustar startsAt/endsAt.", {"id": {"type": "string", "pattern": "^gid://shopify/DiscountCodeNode/[0-9]+$"}, "action": {"type": "string", "enum": ["ACTIVATE", "DEACTIVATE"]}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "action", "confirmationToken"], write=True), "set_discount_code_status", "discounts", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_discount_code_delete", "Prepara exclusão definitiva do cupom e mostra uso acumulado e configuração.", {"id": {"type": "string", "pattern": "^gid://shopify/DiscountCodeNode/[0-9]+$"}}, ["id"]), "prepare_discount_code_delete", "discounts", False, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_delete_discount_code", "ESCRITA DESTRUTIVA: exclui definitivamente o cupom previamente confirmado.", {"id": {"type": "string", "pattern": "^gid://shopify/DiscountCodeNode/[0-9]+$"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_discount_code", "discounts", True, frozenset({"orders", "full"})),
    ToolDefinition(_tool("shopify_list_pages", "Lista e pesquisa páginas da loja com publicação, SEO e resumo do conteúdo.", SEARCH_PAGE), "list_pages", "content"),
    ToolDefinition(_tool("shopify_get_page", "Obtém uma página com HTML completo, SEO, template e publicação.", {"id": PAGE_ID}, ["id"]), "get_page", "content"),
    ToolDefinition(_tool("shopify_prepare_page_create", "Prepara criação de página; publicação deve ser escolhida explicitamente.", PAGE_FIELDS, ["title", "isPublished"]), "prepare_page_create", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_page", "ESCRITA: cria a página exatamente conforme preview confirmado.", {**PAGE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["title", "isPublished", "confirmationToken"], write=True), "create_page", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_page_update", "Consulta conteúdo atual e prepara atualização parcial com diff.", {"id": PAGE_ID, **PAGE_FIELDS, "redirectNewHandle": {"type": "boolean"}}, ["id"]), "prepare_page_update", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_page", "ESCRITA: atualiza a página conforme diff previamente confirmado.", {"id": PAGE_ID, **PAGE_FIELDS, "redirectNewHandle": {"type": "boolean"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_page", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_page_delete", "Prepara exclusão permanente mostrando conteúdo e publicação atuais.", {"id": PAGE_ID}, ["id"]), "prepare_page_delete", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_page", "ESCRITA DESTRUTIVA: exclui definitivamente a página confirmada.", {"id": PAGE_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_page", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_url_redirects", "Lista e pesquisa redirects da loja por caminho ou destino.", SEARCH_PAGE), "list_url_redirects", "navigation"),
    ToolDefinition(_tool("shopify_get_url_redirect", "Obtém redirect pelo GID.", {"id": URL_REDIRECT_ID}, ["id"]), "get_url_redirect", "navigation"),
    ToolDefinition(_tool("shopify_prepare_url_redirect_create", "Verifica conflito de caminho e loop direto antes de criar redirect.", URL_REDIRECT_FIELDS, ["path", "target"]), "prepare_url_redirect_create", "navigation", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_url_redirect", "ESCRITA: cria redirect previamente confirmado.", {**URL_REDIRECT_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["path", "target", "confirmationToken"], write=True), "create_url_redirect", "navigation", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_url_redirect_update", "Consulta estado atual e prepara alteração do redirect.", {"id": URL_REDIRECT_ID, **URL_REDIRECT_FIELDS}, ["id", "path", "target"]), "prepare_url_redirect_update", "navigation", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_url_redirect", "ESCRITA: atualiza redirect conforme preview confirmado.", {"id": URL_REDIRECT_ID, **URL_REDIRECT_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "path", "target", "confirmationToken"], write=True), "update_url_redirect", "navigation", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_url_redirect_delete", "Prepara exclusão definitiva do redirect.", {"id": URL_REDIRECT_ID}, ["id"]), "prepare_url_redirect_delete", "navigation", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_url_redirect", "ESCRITA DESTRUTIVA: exclui o redirect confirmado.", {"id": URL_REDIRECT_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_url_redirect", "navigation", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_menus", "Lista menus de navegação e sua hierarquia de até três níveis.", SEARCH_PAGE), "list_menus", "navigation"),
    ToolDefinition(_tool("shopify_get_menu", "Obtém menu completo e informa se é um menu padrão protegido.", {"id": MENU_ID}, ["id"]), "get_menu", "navigation"),
    ToolDefinition(_tool("shopify_prepare_menu_create", "Valida handle, hierarquia, URLs e recursos antes de criar menu.", MENU_CREATE_FIELDS, ["title", "handle", "items"]), "prepare_menu_create", "navigation", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_menu", "ESCRITA: cria menu completo previamente confirmado.", {**MENU_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["title", "handle", "items", "confirmationToken"], write=True), "create_menu", "navigation", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_menu_update", "Prepara substituição completa e ordenada da árvore do menu.", {"id": MENU_ID, "title": MENU_CREATE_FIELDS["title"], "handle": MENU_CREATE_FIELDS["handle"], "items": {"type": "array", "maxItems": 50, "items": _menu_item_schema(3, update=True)}}, ["id", "title", "items"]), "prepare_menu_update", "navigation", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_menu", "ESCRITA: substitui título e árvore do menu conforme preview confirmado.", {"id": MENU_ID, "title": MENU_CREATE_FIELDS["title"], "handle": MENU_CREATE_FIELDS["handle"], "items": {"type": "array", "maxItems": 50, "items": _menu_item_schema(3, update=True)}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "title", "items", "confirmationToken"], write=True), "update_menu", "navigation", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_menu_delete", "Prepara exclusão e rejeita menus padrão protegidos.", {"id": MENU_ID}, ["id"]), "prepare_menu_delete", "navigation", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_menu", "ESCRITA DESTRUTIVA: exclui menu não padrão previamente confirmado.", {"id": MENU_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_menu", "navigation", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_blogs", "Lista e pesquisa blogs, política de comentários e feed.", SEARCH_PAGE), "list_blogs", "content"),
    ToolDefinition(_tool("shopify_get_blog", "Obtém blog e uma página de artigos.", {"id": BLOG_ID, **PAGE}, ["id"]), "get_blog", "content"),
    ToolDefinition(_tool("shopify_prepare_blog_create", "Valida handle e prepara criação do blog.", BLOG_FIELDS, ["title", "commentPolicy"]), "prepare_blog_create", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_blog", "ESCRITA: cria blog previamente confirmado.", {**BLOG_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["title", "commentPolicy", "confirmationToken"], write=True), "create_blog", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_blog_update", "Consulta configuração atual e prepara atualização parcial do blog.", {"id": BLOG_ID, **BLOG_FIELDS}, ["id"]), "prepare_blog_update", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_blog", "ESCRITA: atualiza blog conforme diff confirmado.", {"id": BLOG_ID, **BLOG_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_blog", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_blog_delete", "Mostra artigos existentes e exige política explícita antes de excluir o blog.", {"id": BLOG_ID, "allowDeleteWithArticles": {"type": "boolean"}}, ["id", "allowDeleteWithArticles"]), "prepare_blog_delete", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_blog", "ESCRITA DESTRUTIVA: exclui definitivamente o blog confirmado.", {"id": BLOG_ID, "allowDeleteWithArticles": {"type": "boolean"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "allowDeleteWithArticles", "confirmationToken"], write=True, destructive=True), "delete_blog", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_articles", "Lista e pesquisa artigos de todos os blogs com publicação e SEO.", SEARCH_PAGE), "list_articles", "content"),
    ToolDefinition(_tool("shopify_get_article", "Obtém artigo com HTML, autor, blog, imagem, tags e publicação.", {"id": ARTICLE_ID}, ["id"]), "get_article", "content"),
    ToolDefinition(_tool("shopify_prepare_article_create", "Valida blog, handle, autor, HTML e publicação antes de criar artigo.", ARTICLE_FIELDS, ["blogId", "title", "authorName", "isPublished"]), "prepare_article_create", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_article", "ESCRITA: cria artigo previamente confirmado.", {**ARTICLE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["blogId", "title", "authorName", "isPublished", "confirmationToken"], write=True), "create_article", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_article_update", "Consulta artigo atual e prepara atualização parcial, inclusive redirect de handle.", {"id": ARTICLE_ID, **ARTICLE_FIELDS, "redirectNewHandle": {"type": "boolean"}}, ["id"]), "prepare_article_update", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_article", "ESCRITA: atualiza artigo conforme preview confirmado.", {"id": ARTICLE_ID, **ARTICLE_FIELDS, "redirectNewHandle": {"type": "boolean"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_article", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_article_delete", "Prepara exclusão permanente do artigo.", {"id": ARTICLE_ID}, ["id"]), "prepare_article_delete", "content", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_article", "ESCRITA DESTRUTIVA: exclui definitivamente o artigo confirmado.", {"id": ARTICLE_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_article", "content", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_get_metafield", "Obtém um metafield por owner, namespace e key, incluindo compareDigest para controle de concorrência.", {"ownerId": METAFIELD_OWNER_ID, "namespace": METAFIELD_NAMESPACE, "key": METAFIELD_KEY}, ["ownerId", "namespace", "key"]), "get_metafield", "metafields"),
    ToolDefinition(_tool("shopify_prepare_metafields_set", "Valida owners, tipos e compareDigest e prepara gravação atômica de até 25 metafields.", METAFIELD_SET_FIELDS, ["metafields"]), "prepare_metafields_set", "metafields", False, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_metafields_set", "ESCRITA: grava atomicamente metafields previamente confirmados usando compare-and-set Shopify.", {**METAFIELD_SET_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["metafields", "confirmationToken"], write=True), "metafields_set", "metafields", True, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_metafields_delete", "Valida existência e digest atual antes de preparar exclusão de até 25 metafields.", METAFIELD_DELETE_FIELDS, ["metafields"]), "prepare_metafields_delete", "metafields", False, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_metafields_delete", "ESCRITA DESTRUTIVA: revalida cada digest imediatamente antes de excluir os metafields confirmados.", {**METAFIELD_DELETE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["metafields", "confirmationToken"], write=True, destructive=True), "metafields_delete", "metafields", True, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_list_metafield_definitions", "Lista o schema de metafields por tipo de owner, com validações e posição no admin.", {"ownerType": {"type": "string", "enum": METAFIELD_OWNER_TYPES}, **SEARCH_PAGE}, ["ownerType"]), "list_metafield_definitions", "metafield_definitions"),
    ToolDefinition(_tool("shopify_get_metafield_definition", "Obtém uma definição de metafield pelo GID.", {"id": METAFIELD_DEFINITION_ID}, ["id"]), "get_metafield_definition", "metafield_definitions"),
    ToolDefinition(_tool("shopify_prepare_metafield_definition_create", "Verifica conflito e prepara criação de schema tipado para metafields.", METAFIELD_DEFINITION_CREATE_FIELDS, ["name", "namespace", "key", "ownerType", "type", "pin"]), "prepare_metafield_definition_create", "metafield_definitions", False, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_create_metafield_definition", "ESCRITA: cria a definição de metafield previamente confirmada.", {**METAFIELD_DEFINITION_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["name", "namespace", "key", "ownerType", "type", "pin", "confirmationToken"], write=True), "create_metafield_definition", "metafield_definitions", True, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_metafield_definition_update", "Consulta a definição atual e prepara alteração de nome, descrição ou validações.", METAFIELD_DEFINITION_UPDATE_FIELDS, ["namespace", "key", "ownerType"]), "prepare_metafield_definition_update", "metafield_definitions", False, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_update_metafield_definition", "ESCRITA: atualiza a configuração mutável da definição confirmada.", {**METAFIELD_DEFINITION_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["namespace", "key", "ownerType", "confirmationToken"], write=True), "update_metafield_definition", "metafield_definitions", True, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_prepare_metafield_definition_delete", "Mostra o schema e exige política explícita para preservar ou apagar metafields associados.", {"id": METAFIELD_DEFINITION_ID, "deleteAllAssociatedMetafields": {"type": "boolean"}}, ["id", "deleteAllAssociatedMetafields"]), "prepare_metafield_definition_delete", "metafield_definitions", False, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_delete_metafield_definition", "ESCRITA DESTRUTIVA: exclui a definição e, se confirmado, agenda exclusão de todos os valores associados.", {"id": METAFIELD_DEFINITION_ID, "deleteAllAssociatedMetafields": {"type": "boolean"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "deleteAllAssociatedMetafields", "confirmationToken"], write=True, destructive=True), "delete_metafield_definition", "metafield_definitions", True, frozenset({"catalog", "orders", "full"})),
    ToolDefinition(_tool("shopify_list_metaobject_definitions", "Lista schemas de metaobjects, campos, acessos e capacidades.", PAGE), "list_metaobject_definitions", "metaobjects"),
    ToolDefinition(_tool("shopify_get_metaobject_definition", "Obtém o schema completo de metaobject por GID.", {"id": METAOBJECT_DEFINITION_ID}, ["id"]), "get_metaobject_definition", "metaobjects"),
    ToolDefinition(_tool("shopify_get_metaobject_definition_by_type", "Obtém o schema completo pelo type imutável.", {"type": METAOBJECT_TYPE}, ["type"]), "get_metaobject_definition_by_type", "metaobjects"),
    ToolDefinition(_tool("shopify_prepare_metaobject_definition_create", "Valida chaves, display name e conflito antes de criar um schema de metaobject.", METAOBJECT_DEFINITION_CREATE_FIELDS, ["name", "type", "fieldDefinitions"]), "prepare_metaobject_definition_create", "metaobjects", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_metaobject_definition", "ESCRITA: cria o schema de metaobject previamente confirmado.", {**METAOBJECT_DEFINITION_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["name", "type", "fieldDefinitions", "confirmationToken"], write=True), "create_metaobject_definition", "metaobjects", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_metaobject_definition_update", "Valida operações create/update/delete de fields e prepara alteração estrutural do schema.", METAOBJECT_DEFINITION_UPDATE_FIELDS, ["id", "acknowledgeFieldDataLoss"]), "prepare_metaobject_definition_update", "metaobjects", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_metaobject_definition", "ESCRITA: altera o schema confirmado; remoções de fields exigem reconhecimento explícito de perda de dados.", {**METAOBJECT_DEFINITION_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "acknowledgeFieldDataLoss", "confirmationToken"], write=True, destructive=True), "update_metaobject_definition", "metaobjects", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_metaobject_definition_delete", "Prepara exclusão em cascata da definição, instâncias, metafield definitions e metafields relacionados.", {"id": METAOBJECT_DEFINITION_ID, "confirmCascade": {"type": "boolean"}}, ["id", "confirmCascade"]), "prepare_metaobject_definition_delete", "metaobjects", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_metaobject_definition", "ESCRITA DESTRUTIVA: exclui assincronamente todo o grafo associado à definição confirmada.", {"id": METAOBJECT_DEFINITION_ID, "confirmCascade": {"type": "boolean"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmCascade", "confirmationToken"], write=True, destructive=True), "delete_metaobject_definition", "metaobjects", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_metaobjects", "Lista e pesquisa instâncias de um type de metaobject.", {"type": METAOBJECT_TYPE, **SEARCH_PAGE}, ["type"]), "list_metaobjects", "metaobjects"),
    ToolDefinition(_tool("shopify_get_metaobject", "Obtém uma instância e seus campos por GID.", {"id": METAOBJECT_ID}, ["id"]), "get_metaobject", "metaobjects"),
    ToolDefinition(_tool("shopify_get_metaobject_by_handle", "Obtém instância pelo par type/handle.", {"type": METAOBJECT_TYPE, "handle": METAOBJECT_HANDLE}, ["type", "handle"]), "get_metaobject_by_handle", "metaobjects"),
    ToolDefinition(_tool("shopify_prepare_metaobject_create", "Valida a instância contra o schema e verifica conflito de handle.", METAOBJECT_CREATE_FIELDS, ["type", "fields"]), "prepare_metaobject_create", "metaobjects", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_metaobject", "ESCRITA: cria instância estruturada previamente confirmada.", {**METAOBJECT_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["type", "fields", "confirmationToken"], write=True), "create_metaobject", "metaobjects", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_metaobject_update", "Consulta estado e prepara patch de campos, handle ou publicação.", METAOBJECT_UPDATE_FIELDS, ["id"]), "prepare_metaobject_update", "metaobjects", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_metaobject", "ESCRITA: aplica patch de metaobject previamente confirmado.", {**METAOBJECT_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_metaobject", "metaobjects", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_metaobject_delete", "Mostra os campos antes de preparar exclusão permanente e alerta sobre referências externas.", {"id": METAOBJECT_ID}, ["id"]), "prepare_metaobject_delete", "metaobjects", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_metaobject", "ESCRITA DESTRUTIVA: exclui a instância e metafields associados.", {"id": METAOBJECT_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_metaobject", "metaobjects", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_files", "Lista e pesquisa arquivos polimórficos, status de processamento, erros e URLs CDN.", SEARCH_PAGE), "list_files", "files"),
    ToolDefinition(_tool("shopify_get_file", "Obtém arquivo, mídia ou vídeo pelo GID e retorna estado assíncrono.", {"id": FILE_ID}, ["id"]), "get_file", "files"),
    ToolDefinition(_tool("shopify_prepare_files_create", "Prepara até 25 arquivos HTTPS/staged e exige política explícita para nomes duplicados.", FILE_CREATE_FIELDS, ["files"]), "prepare_files_create", "files", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_files_create", "ESCRITA: inicia processamento assíncrono dos arquivos previamente confirmados.", {**FILE_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["files", "confirmationToken"], write=True), "files_create", "files", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_files_update", "Valida arquivos e referências de produto antes de alterar conteúdo ou metadados.", FILE_UPDATE_FIELDS, ["files"]), "prepare_files_update", "files", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_files_update", "ESCRITA: atualiza arquivos e associações de produto conforme preview confirmado.", {**FILE_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["files", "confirmationToken"], write=True), "files_update", "files", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_files_delete", "Consulta arquivos e exige confirmação da remoção de referências antes da exclusão permanente.", FILE_DELETE_FIELDS, ["fileIds", "confirmRemoveReferences"]), "prepare_files_delete", "files", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_files_delete", "ESCRITA DESTRUTIVA: remove arquivos e suas associações/referências confirmadas.", {**FILE_DELETE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["fileIds", "confirmRemoveReferences", "confirmationToken"], write=True, destructive=True), "files_delete", "files", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_staged_uploads_create", "Valida metadados e prepara URLs temporárias; não lê nem envia bytes ou caminhos locais.", STAGED_UPLOAD_FIELDS, ["input"]), "prepare_staged_uploads_create", "files", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_staged_uploads_create", "ESCRITA: gera alvos temporários para upload direto à Shopify.", {**STAGED_UPLOAD_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["input", "confirmationToken"], write=True), "staged_uploads_create", "files", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_get_publication_status", "Consulta em quais publicações informadas um produto ou coleção está disponível.", {"id": PUBLISHABLE_ID, "publicationIds": UNPUBLISH_FIELDS["publicationIds"]}, ["id", "publicationIds"]), "get_publication_status", "publications"),
    ToolDefinition(_tool("shopify_prepare_publish", "Valida recurso, canais e agendamento e prepara publicação explícita.", PUBLISH_FIELDS, ["id", "publications"]), "prepare_publish", "publications", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_publish", "ESCRITA: publica produto ou coleção nos canais confirmados.", {**PUBLISH_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "publications", "confirmationToken"], write=True), "publish", "publications", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_unpublish", "Mostra disponibilidade atual e prepara remoção explícita dos canais.", UNPUBLISH_FIELDS, ["id", "publicationIds"]), "prepare_unpublish", "publications", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_unpublish", "ESCRITA: remove produto ou coleção das publicações confirmadas.", {**UNPUBLISH_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "publicationIds", "confirmationToken"], write=True, destructive=True), "unpublish", "publications", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_markets", "Lista mercados, regiões, moedas, catálogos e presença web.", SEARCH_PAGE), "list_markets", "markets"),
    ToolDefinition(_tool("shopify_get_market", "Obtém configuração comercial completa de um mercado por GID.", {"id": MARKET_ID}, ["id"]), "get_market", "markets"),
    ToolDefinition(_tool("shopify_prepare_market_create", "Valida regiões, moeda, catálogos e conflito de handle antes de criar mercado.", MARKET_CREATE_FIELDS, ["name", "status", "conditions", "makeDuplicateUniqueMarketsDraft"]), "prepare_market_create", "markets", False, frozenset({"full"})),
    ToolDefinition(_tool("shopify_market_create", "ESCRITA: cria mercado conforme configuração confirmada.", {**MARKET_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["name", "status", "conditions", "makeDuplicateUniqueMarketsDraft", "confirmationToken"], write=True), "market_create", "markets", True, frozenset({"full"})),
    ToolDefinition(_tool("shopify_prepare_market_update", "Consulta o mercado e prepara mudanças de regiões, moeda, status e catálogos.", MARKET_UPDATE_FIELDS, ["id"]), "prepare_market_update", "markets", False, frozenset({"full"})),
    ToolDefinition(_tool("shopify_market_update", "ESCRITA: atualiza o mercado conforme preview confirmado.", {**MARKET_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "market_update", "markets", True, frozenset({"full"})),
    ToolDefinition(_tool("shopify_prepare_market_delete", "Mostra regiões, catálogos e presença web e exige confirmação da remoção da definição do mercado.", {"id": MARKET_ID, "confirmAssignmentsRemoval": {"type": "boolean"}}, ["id", "confirmAssignmentsRemoval"]), "prepare_market_delete", "markets", False, frozenset({"full"})),
    ToolDefinition(_tool("shopify_market_delete", "ESCRITA DESTRUTIVA: exclui permanentemente a definição do mercado confirmada.", {"id": MARKET_ID, "confirmAssignmentsRemoval": {"type": "boolean"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmAssignmentsRemoval", "confirmationToken"], write=True, destructive=True), "market_delete", "markets", True, frozenset({"full"})),
    ToolDefinition(_tool("shopify_list_catalogs", "Lista catálogos de Markets, B2B e apps com publicação e price list.", SEARCH_PAGE), "list_catalogs", "catalogs"),
    ToolDefinition(_tool("shopify_get_catalog", "Obtém catálogo e seu contexto, publicação e price list.", {"id": CATALOG_ID}, ["id"]), "get_catalog", "catalogs"),
    ToolDefinition(_tool("shopify_list_price_lists", "Lista price lists e ajustes contextuais associados a catálogos.", SEARCH_PAGE), "list_price_lists", "pricing"),
    ToolDefinition(_tool("shopify_get_price_list", "Obtém price list e preços de variantes paginados.", {"id": PRICE_LIST_ID, **SEARCH_PAGE}, ["id"]), "get_price_list", "pricing"),
    ToolDefinition(_tool("shopify_prepare_fixed_prices_add", "Valida variantes, moeda e preços atuais antes de criar ou substituir preços fixos.", FIXED_PRICES_ADD_FIELDS, ["priceListId", "prices"]), "prepare_fixed_prices_add", "pricing", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_fixed_prices_add", "ESCRITA: cria ou substitui preços fixos confirmados para variantes.", {**FIXED_PRICES_ADD_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["priceListId", "prices", "confirmationToken"], write=True), "fixed_prices_add", "pricing", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_fixed_prices_delete", "Mostra preços atuais e prepara retorno das variantes ao ajuste padrão da price list.", FIXED_PRICES_DELETE_FIELDS, ["priceListId", "variantIds"]), "prepare_fixed_prices_delete", "pricing", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_fixed_prices_delete", "ESCRITA DESTRUTIVA: remove preços fixos e restaura o cálculo padrão da price list.", {**FIXED_PRICES_DELETE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["priceListId", "variantIds", "confirmationToken"], write=True, destructive=True), "fixed_prices_delete", "pricing", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_webhook_subscriptions", "Lista subscriptions shop-scoped deste app, endpoints, tópicos e filtros.", SEARCH_PAGE), "list_webhook_subscriptions", "webhooks"),
    ToolDefinition(_tool("shopify_get_webhook_subscription", "Obtém uma subscription e a API version herdada do app.", {"id": WEBHOOK_ID}, ["id"]), "get_webhook_subscription", "webhooks"),
    ToolDefinition(_tool("shopify_prepare_webhook_create", "Valida endpoint, tópico e payload antes de registrar entrega de eventos.", WEBHOOK_CREATE_FIELDS, ["topic", "uri", "format"]), "prepare_webhook_create", "webhooks", False, frozenset({"full"})),
    ToolDefinition(_tool("shopify_webhook_create", "ESCRITA: cria subscription shop-scoped previamente confirmada.", {**WEBHOOK_CREATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["topic", "uri", "format", "confirmationToken"], write=True), "webhook_create", "webhooks", True, frozenset({"full"})),
    ToolDefinition(_tool("shopify_prepare_webhook_update", "Consulta configuração atual e prepara alteração atômica do endpoint ou payload.", WEBHOOK_UPDATE_FIELDS, ["id"]), "prepare_webhook_update", "webhooks", False, frozenset({"full"})),
    ToolDefinition(_tool("shopify_webhook_update", "ESCRITA: atualiza subscription conforme diff confirmado.", {**WEBHOOK_UPDATE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "webhook_update", "webhooks", True, frozenset({"full"})),
    ToolDefinition(_tool("shopify_prepare_webhook_delete", "Mostra tópico e endpoint antes de preparar interrupção permanente da entrega.", {"id": WEBHOOK_ID}, ["id"]), "prepare_webhook_delete", "webhooks", False, frozenset({"full"})),
    ToolDefinition(_tool("shopify_webhook_delete", "ESCRITA DESTRUTIVA: remove a subscription e interrompe eventos futuros.", {"id": WEBHOOK_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "webhook_delete", "webhooks", True, frozenset({"full"})),
    ToolDefinition(_tool("shopify_list_bulk_operations", "Lista e filtra jobs assíncronos de exportação/importação deste app na API moderna.", SEARCH_PAGE), "list_bulk_operations", "bulk_operations"),
    ToolDefinition(_tool("shopify_get_bulk_operation", "Consulta status, progresso, erros e URLs temporárias de um job Bulk pelo GID.", {"id": BULK_OPERATION_ID}, ["id"]), "get_bulk_operation", "bulk_operations"),
    ToolDefinition(_tool("shopify_prepare_bulk_export", "Gera internamente uma exportação JSONL de formato conhecido; não aceita GraphQL arbitrário.", BULK_EXPORT_FIELDS, ["resource"]), "prepare_bulk_export", "bulk_operations", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_start_bulk_export", "ESCRITA: inicia a exportação Bulk previamente preparada e retorna um job para acompanhamento.", {**BULK_EXPORT_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["resource", "confirmationToken"], write=True), "start_bulk_export", "bulk_operations", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_bulk_operation_cancel", "Consulta o job e prepara o cancelamento somente se ainda estiver ativo.", {"id": BULK_OPERATION_ID}, ["id"]), "prepare_bulk_operation_cancel", "bulk_operations", False, frozenset({"full"})),
    ToolDefinition(_tool("shopify_cancel_bulk_operation", "ESCRITA DESTRUTIVA: solicita cancelamento do job Bulk confirmado; pode haver atraso até CANCELED.", {"id": BULK_OPERATION_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "cancel_bulk_operation", "bulk_operations", True, frozenset({"full"})),
    ToolDefinition(_tool("shopify_prepare_bulk_import_staged_upload", "Prepara um alvo POST exclusivo para JSONL de variáveis Bulk; o MCP não lê nem envia o arquivo.", BULK_IMPORT_STAGE_FIELDS, ["filename", "fileSize"]), "prepare_bulk_import_staged_upload", "bulk_operations", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_bulk_import_staged_upload", "ESCRITA: gera credenciais temporárias para upload direto do JSONL à Shopify.", {**BULK_IMPORT_STAGE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["filename", "fileSize", "confirmationToken"], write=True), "create_bulk_import_staged_upload", "bulk_operations", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_bulk_import", "Prepara importação por mutation interna conhecida, vinculada ao path, hash e quantidade de linhas declarados.", BULK_IMPORT_FIELDS, ["kind", "stagedUploadPath", "clientIdentifier", "lineCount", "sha256", "acknowledgeUnorderedExecution"]), "prepare_bulk_import", "bulk_operations", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_start_bulk_import", "ESCRITA: inicia importação Bulk previamente preparada; cada linha JSONL é executada independentemente e fora de ordem.", {**BULK_IMPORT_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["kind", "stagedUploadPath", "clientIdentifier", "lineCount", "sha256", "acknowledgeUnorderedExecution", "confirmationToken"], write=True), "start_bulk_import", "bulk_operations", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_customers", "Pesquisa clientes e resume pedidos e valor gasto.", SEARCH_PAGE), "list_customers", "customers"),
    ToolDefinition(_tool("shopify_get_customer", "Obtém perfil, consentimentos, endereços e histórico resumido do cliente. Contém PII.", {"id": {"type": "string", "pattern": "^gid://shopify/Customer/[0-9]+$"}, **PAGE}, ["id"]), "get_customer", "customers"),
    ToolDefinition(_tool("shopify_count_customers", "Conta clientes por filtros Shopify e informa a precisão.", {"query": {"type": "string", "maxLength": 1000}, "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 1000000}}, []), "count_customers", "customers"),
    ToolDefinition(_tool("shopify_list_collections", "Lista coleções com SEO e contagem de produtos.", SEARCH_PAGE), "list_collections", "collections"),
    ToolDefinition(_tool("shopify_get_collection", "Obtém coleção, SEO, imagem, contagem e regras pelo GID.", {"id": {"type": "string", "pattern": "^gid://shopify/Collection/[0-9]+$"}}, ["id"]), "get_collection", "collections"),
    ToolDefinition(_tool("shopify_get_collection_by_handle", "Obtém coleção pelo handle exato.", {"handle": {"type": "string", "pattern": "^[a-z0-9]+(?:-[a-z0-9]+)*$", "maxLength": 255}}, ["handle"]), "get_collection_by_handle", "collections"),
    ToolDefinition(_tool("shopify_list_collection_products", "Lista produtos de uma coleção e informa se ela é automática.", {"id": {"type": "string", "pattern": "^gid://shopify/Collection/[0-9]+$"}, **PAGE}, ["id"]), "list_collection_products", "collections"),
    ToolDefinition(_tool("shopify_list_collection_rule_conditions", "Lista condições e relações aceitas para regras de coleções automáticas.", {}), "list_collection_rule_conditions", "collections"),
    ToolDefinition(_tool("shopify_prepare_collection_create", "Prepara criação de coleção não publicada usando o contrato moderno CollectionCreateInput.", COLLECTION_BASE_FIELDS, ["title"]), "prepare_collection_create", "collections", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_create_collection", "ESCRITA: cria coleção não publicada previamente preparada.", {**COLLECTION_BASE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["title", "confirmationToken"], write=True), "create_collection", "collections", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_collection_update", "Consulta estado atual e prepara atualização dos metadados da coleção.", {"id": COLLECTION_ID, **COLLECTION_BASE_FIELDS}, ["id"]), "prepare_collection_update", "collections", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_collection", "ESCRITA: atualiza coleção previamente preparada pelo contrato moderno.", {"id": COLLECTION_ID, **COLLECTION_BASE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_collection", "collections", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_collection_delete", "Prepara exclusão irreversível da coleção; os produtos permanecem na loja.", {"id": COLLECTION_ID}, ["id"]), "prepare_collection_delete", "collections", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_delete_collection", "ESCRITA DESTRUTIVA: exclui permanentemente a coleção previamente confirmada.", {"id": COLLECTION_ID, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True, destructive=True), "delete_collection", "collections", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_list_locations", "Lista locais de estoque, inclusive inativos.", PAGE), "list_locations", "locations"),
    ToolDefinition(_tool("shopify_list_inventory_items", "Pesquisa itens de estoque por SKU, ID ou datas e retorna níveis por local.", SEARCH_PAGE), "list_inventory_items", "inventory"),
    ToolDefinition(_tool("shopify_get_inventory_item", "Obtém item de estoque e quantidades por local, inclusive níveis inativos.", {"id": INVENTORY_ITEM_ID, **PAGE}, ["id"]), "get_inventory_item", "inventory"),
    ToolDefinition(_tool("shopify_list_low_stock_variants", "Lista variantes com estoque agregado menor ou igual ao limite, ordenadas pelo menor saldo.", {"threshold": {"type": "integer", "minimum": -1000000000, "maximum": 1000000000, "default": 5}, "locationId": LOCATION_ID, **PAGE}), "list_low_stock_variants", "composite_views"),
    ToolDefinition(_tool("shopify_prepare_inventory_adjust", "Valida item/local e quantidade atual antes de preparar deltas de estoque com compare-and-swap.", INVENTORY_ADJUST_FIELDS, ["name", "reason", "referenceDocumentUri", "changes"]), "prepare_inventory_adjust", "inventory", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_inventory_adjust", "ESCRITA: aplica deltas de estoque preparados, com CAS e chave de idempotência Shopify.", {**INVENTORY_ADJUST_FIELDS, "idempotencyKey": {"type": "string", "format": "uuid"}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["name", "reason", "referenceDocumentUri", "changes", "idempotencyKey", "confirmationToken"], write=True), "inventory_adjust", "inventory", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_inventory_activation_toggle", "Consulta níveis e prepara ativação/desativação em locais; desativar remove suas quantidades.", INVENTORY_TOGGLE_FIELDS, ["inventoryItemId", "updates"]), "prepare_inventory_activation_toggle", "inventory", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_inventory_activation_toggle", "ESCRITA: ativa ou desativa um item nos locais previamente confirmados.", {**INVENTORY_TOGGLE_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["inventoryItemId", "updates", "confirmationToken"], write=True), "inventory_activation_toggle", "inventory", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_inventory_item_weight_update", "Consulta o peso atual do item de estoque e prepara a alteração de measurement.weight (before/after + token).", INVENTORY_ITEM_WEIGHT_FIELDS, ["inventoryItemId", "weight"]), "prepare_inventory_item_weight_update", "inventory", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_inventory_item_weight_update", "ESCRITA: aplica o peso previamente preparado no item de estoque (inventoryItemUpdate measurement.weight).", {**INVENTORY_ITEM_WEIGHT_FIELDS, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["inventoryItemId", "weight", "confirmationToken"], write=True), "inventory_item_weight_update", "inventory", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_tags_change", "Prepara adição/remoção de tags, retorna before/after e token de confirmação de uso único.", {"id": {"type": "string", "pattern": "^gid://shopify/[A-Za-z]+/[0-9]+$"}, "action": {"type": "string", "enum": ["add", "remove"]}, "tags": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 255}, "minItems": 1, "maxItems": 250, "uniqueItems": True}}, ["id", "action", "tags"]), "prepare_tags_change", "products", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_prepare_product_seo_update", "Prepara alteração de SEO, retorna before/after e token de confirmação de uso único.", {"id": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"}, "title": {"type": "string", "minLength": 1, "maxLength": 70}, "description": {"type": "string", "minLength": 1, "maxLength": 320}}, ["id"]), "prepare_product_seo_update", "products", False, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_add_tags", "ESCRITA: aplica adição de tags previamente preparada. Token é de uso único.", {"id": {"type": "string", "pattern": "^gid://shopify/[A-Za-z]+/[0-9]+$"}, "tags": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 255}, "minItems": 1, "maxItems": 250, "uniqueItems": True}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "tags", "confirmationToken"], write=True), "add_tags", "products", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_remove_tags", "ESCRITA: aplica remoção de tags previamente preparada. Token é de uso único.", {"id": {"type": "string", "pattern": "^gid://shopify/[A-Za-z]+/[0-9]+$"}, "tags": {"type": "array", "items": {"type": "string", "minLength": 1, "maxLength": 255}, "minItems": 1, "maxItems": 250, "uniqueItems": True}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "tags", "confirmationToken"], write=True), "remove_tags", "products", True, frozenset({"catalog", "full"})),
    ToolDefinition(_tool("shopify_update_product_seo", "ESCRITA: aplica SEO previamente preparado. Token é de uso único.", {"id": {"type": "string", "pattern": "^gid://shopify/Product/[0-9]+$"}, "title": {"type": "string", "minLength": 1, "maxLength": 70}, "description": {"type": "string", "minLength": 1, "maxLength": 320}, "confirmationToken": {"type": "string", "minLength": 32, "maxLength": 256}}, ["id", "confirmationToken"], write=True), "update_product_seo", "products", True, frozenset({"catalog", "full"})),
]

BY_NAME = {definition.tool.name: definition for definition in DEFINITIONS}


def enabled_definitions(profile: str, writes_enabled: bool) -> list[ToolDefinition]:
    return [definition for definition in DEFINITIONS if profile in definition.profiles and (not definition.write or writes_enabled)]
