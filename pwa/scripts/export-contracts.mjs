import {
    OfficialEvidenceMetadataSchema,
    OfficialEvidenceReceiptSchema,
} from "../src/domain/official-evidence.ts";
import {
    PackagingSchema,
    SnapshotScopeSchema,
} from "../src/domain/product-units.ts";
import { CatalogRowSchema } from "../src/data/catalog.ts";
import { OrderRevisionSchema } from "../src/domain/order-revision-contracts.ts";
import { TripCloseSchema } from "../src/domain/trip-close-contracts.ts";
import { DeliveryRequestSchema } from "../src/domain/delivery-approval.ts";
import { z } from "zod";
import {
    CollectionTaskSchema,
    CollectionReceiptSchema,
} from "../src/domain/collection-contracts.ts";
import { readFileSync, writeFileSync } from "node:fs";
import {
    CommandSchema,
    ReceiptSchema,
    IdentitySchema,
    SnapshotSchema,
} from "../src/domain/contracts.ts";
import {
    DeliveryPodSchema,
    DeliveryTaskSchema,
} from "../src/domain/delivery-contracts.ts";
import { ExpenseRequestSchema } from "../src/domain/expense.ts";
import { ExpenseRealizationSchema } from "../src/domain/settlement-contracts.ts";
import {
    VisitCheckInSchema,
    VisitCheckoutSchema,
    VisitOrderSchema,
} from "../src/domain/visit-contracts.ts";
// JSON Schema does not infer Zod superRefine: preserve the visit photo pair
// in both standalone DTOs and Command payload branches, while allowing legacy.
function photoPairDependencies(schema) {
    if (!schema || typeof schema !== "object") return;
    if (schema.properties?.evidence_version && schema.properties?.evidence)
        schema.dependentRequired = {
            evidence_version: ["evidence"],
            evidence: ["evidence_version"],
        };
    if (
        (schema.properties?.pod_version ||
            schema.properties?.collection_version) &&
        schema.properties?.supersedes_uuid &&
        schema.properties?.correction_reason
    )
        schema.dependentRequired = {
            ...schema.dependentRequired,
            supersedes_uuid: ["correction_reason"],
            correction_reason: ["supersedes_uuid"],
        };
    if (schema.properties?.collection_version)
        schema.allOf = [
            {
                if: {
                    properties: { method: { const: "transfer" } },
                    required: ["method"],
                },
                then: { required: ["transfer_reference"] },
                else: { not: { required: ["transfer_reference"] } },
            },
        ];
    if (schema.properties?.pod_version)
        schema.allOf = [
            ...(schema.allOf ?? []),
            {
                if: {
                    properties: {
                        source: {
                            properties: { workflow_version: { const: 2 } },
                            required: ["workflow_version"],
                        },
                    },
                    required: ["source"],
                },
                then: { required: ["session", "delivery_status"] },
            },
        ];
    Object.values(schema).forEach(photoPairDependencies);
}
const schemas = Object.fromEntries(
    Object.entries({
        OfficialEvidenceMetadata: OfficialEvidenceMetadataSchema,
        OfficialEvidenceReceipt: OfficialEvidenceReceiptSchema,
        Packaging: PackagingSchema,
        SnapshotScope: SnapshotScopeSchema,
        CatalogRow: CatalogRowSchema,
        OrderRevision: OrderRevisionSchema,
        TripClose: TripCloseSchema,
        DeliveryRequest: DeliveryRequestSchema,
        DeliveryPod: DeliveryPodSchema,
        DeliveryTask: DeliveryTaskSchema,
        CollectionTask: CollectionTaskSchema,
        CollectionReceipt: CollectionReceiptSchema,
        Command: CommandSchema,
        VisitCheckIn: VisitCheckInSchema,
        VisitCheckOut: VisitCheckoutSchema,
        VisitOrder: VisitOrderSchema,
        ExpenseRequest: ExpenseRequestSchema,
        ExpenseRealization: ExpenseRealizationSchema,
        Receipt: ReceiptSchema,
        Identity: IdentitySchema,
        Snapshot: SnapshotSchema,
    }).map(([key, value]) => {
        const schema = z.toJSONSchema(value, { target: "draft-2020-12" });
        delete schema.$schema;
        photoPairDependencies(schema);
        if (key === "Packaging")
            schema["x-invariant"] =
                "carton >= pack; carton % pack = 0; quantities in pcs";
        if (key === "Snapshot")
            schema.allOf = [
                {
                    if: {
                        properties: { catalog_version: { const: 2 } },
                        required: ["catalog_version"],
                    },
                    then: {
                        required: ["scope"],
                        properties: {
                            version: { minLength: 1 },
                            updatedAt: { format: "date-time" },
                            products: {
                                items: {
                                    required: [
                                        "sku_code",
                                        "packaging",
                                        "price_basis",
                                        "stock_basis",
                                    ],
                                },
                                "x-unique": ["id", "sku_code"],
                            },
                        },
                    },
                },
            ];
        return [key, schema];
    }),
);
const response = (name) => ({
    description: "Contract response",
    content: {
        "application/json": {
            schema: { $ref: `#/components/schemas/${name}` },
        },
    },
});
const spec = {
    openapi: "3.1.0",
    info: {
        title: "FMCG Field client contract draft",
        version: "0.15.0",
        description:
            "Bootstrap/snapshot and explicit evidence routes are implemented by id_mobile_api. Business command routes remain draft and unavailable on staging.",
    },
    servers: [{ url: "/api/v1" }],
    paths: {
        "/me/bootstrap": {
            get: {
                responses: {
                    200: response("Identity"),
                    401: { description: "Official session required" },
                },
            },
        },
        "/sync/snapshot": { get: { responses: { 200: response("Snapshot") } } },
        "/outlets/{outlet_id}/image": {
            get: {
                description:
                    "Private native outlet image, current assignment and company only; no-store.",
                parameters: [
                    {
                        name: "outlet_id",
                        in: "path",
                        required: true,
                        schema: { type: "integer", minimum: 1 },
                    },
                ],
                responses: {
                    200: {
                        description: "Raster image",
                        content: {
                            "image/png": {
                                schema: { type: "string", format: "binary" },
                            },
                            "image/jpeg": {
                                schema: { type: "string", format: "binary" },
                            },
                            "image/webp": {
                                schema: { type: "string", format: "binary" },
                            },
                        },
                    },
                    401: { description: "Official session required" },
                    403: {
                        description: "Outlet is not assigned or not readable",
                    },
                    404: { description: "No image available" },
                },
            },
        },
        "/evidence": {
            post: {
                description:
                    "Explicit evidence capability; native Odoo multipart csrf_token. Stores evidence only, not a business command.",
                requestBody: {
                    required: true,
                    content: {
                        "multipart/form-data": {
                            schema: {
                                type: "object",
                                required: ["metadata", "photo", "csrf_token"],
                                additionalProperties: false,
                                properties: {
                                    metadata: {
                                        type: "string",
                                        description:
                                            "JSON OfficialEvidenceMetadata",
                                    },
                                    photo: { type: "string", format: "binary" },
                                    csrf_token: { type: "string" },
                                },
                            },
                        },
                    },
                },
                responses: {
                    201: response("OfficialEvidenceReceipt"),
                    200: response("OfficialEvidenceReceipt"),
                    400: { description: "Invalid native CSRF or request" },
                    403: { description: "Evidence capability or scope denied" },
                    409: { description: "UUID/scope/day conflict" },
                    413: { description: "Upload limit" },
                    422: {
                        description:
                            "Invalid photo, stale fix or geofence not inside",
                    },
                },
            },
        },
        "/evidence/{client_uuid}/{variant}": {
            get: {
                parameters: [
                    {
                        name: "client_uuid",
                        in: "path",
                        required: true,
                        schema: { type: "string", format: "uuid" },
                    },
                    {
                        name: "variant",
                        in: "path",
                        required: true,
                        schema: {
                            type: "string",
                            enum: ["original", "watermarked"],
                        },
                    },
                ],
                responses: {
                    200: {
                        description:
                            "Private owner/company-scoped image; no-store",
                        content: {
                            "image/jpeg": {
                                schema: { type: "string", format: "binary" },
                            },
                            "image/png": {
                                schema: { type: "string", format: "binary" },
                            },
                        },
                    },
                    403: { description: "Evidence role/scope denied" },
                    404: {
                        description:
                            "Image not found in current owner/company scope",
                    },
                },
            },
        },
        "/sync/commands": {
            post: {
                parameters: [
                    {
                        name: "X-CSRF-Token",
                        in: "header",
                        required: true,
                        schema: { type: "string" },
                    },
                ],
                requestBody: {
                    required: true,
                    content: {
                        "application/json": {
                            schema: { $ref: "#/components/schemas/Command" },
                        },
                    },
                },
                responses: {
                    200: response("Receipt"),
                    401: { description: "Session expired" },
                    403: { description: "Operation/scope denied" },
                    409: { description: "Idempotency or revision conflict" },
                    429: { description: "Rate limited; retry policy applies" },
                    503: {
                        description:
                            "Temporary server failure; retry same UUID",
                    },
                },
            },
        },
    },
    components: { schemas },
    "x-status": "read-and-evidence-implemented-business-commands-draft",
    "x-auth": "same-origin cookie; no shared privileged API key",
};
const content = JSON.stringify(spec, null, 2) + "\n";
if (process.argv.includes("--check")) {
    if (readFileSync("contracts/openapi.json", "utf8") !== content)
        throw new Error("Contract drift: run npm run contracts:export");
    console.log("OpenAPI/client schema drift gate PASS");
} else writeFileSync("contracts/openapi.json", content);
