import { z } from "zod";
import { readFileSync, writeFileSync } from "node:fs";
import {
    CommandSchema,
    ReceiptSchema,
    IdentitySchema,
    SnapshotSchema,
} from "../src/domain/contracts.ts";
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
    Object.values(schema).forEach(photoPairDependencies);
}
const schemas = Object.fromEntries(
    Object.entries({
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
        version: "0.6.0",
        description:
            "Client-owned draft. Not an implemented Odoo API. Single command receipt; batch extension requires agreement.",
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
    "x-status": "draft-client-only",
    "x-auth": "same-origin cookie; no shared privileged API key",
};
const content = JSON.stringify(spec, null, 2) + "\n";
if (process.argv.includes("--check")) {
    if (readFileSync("contracts/openapi.json", "utf8") !== content)
        throw new Error("Contract drift: run npm run contracts:export");
    console.log("OpenAPI/client schema drift gate PASS");
} else writeFileSync("contracts/openapi.json", content);
