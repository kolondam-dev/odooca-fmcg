import { z } from "zod";
import { VisitFixSchema } from "./visit-contracts.ts";
export const DemoOfficeSchema = z
    .object({
        id: z.literal("SIM-OFFICE-MANADO"),
        latitude: z.number().min(-90).max(90),
        longitude: z.number().min(-180).max(180),
        radius: z.number().nonnegative(),
        tolerance_m: z.literal(25),
    })
    .strict();
export const DEMO_OFFICE = {
    id: "SIM-OFFICE-MANADO" as const,
    latitude: 1.465,
    longitude: 124.833,
    radius: 30,
    tolerance_m: 25 as const,
};
export const TripCloseSchema = z
    .object({
        trip_id: z.string().min(1),
        business_date: z.iso.date(),
        daily_source: z.unknown(),
        office: DemoOfficeSchema,
        fix: VisitFixSchema,
        pod_uuids: z.array(z.string().uuid()).min(1),
        demo_unrestricted: z.literal(true).optional(),
    })
    .strict();
export const tripCloseKey = (trip: string, date: string) =>
    `trip-close-v1:${JSON.stringify([trip, date])}`;
