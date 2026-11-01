import { z } from "zod";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
export type Page = "home" | "sales" | "delivery" | "hris" | "more" | "expenses";
export type Dialog =
    | { type: "order"; outlet: string }
    | { type: "extra" }
    | { type: "proof"; delivery: string }
    | { type: "expense"; trip?: string }
    | { type: "attendance"; event?: "check_in" | "check_out" }
    | { type: "leave" }
    | { type: "profile" };
export type Route = { page: Page; outlet?: string; dialog?: Dialog };
const DialogSchema = z.discriminatedUnion("type", [
    z.object({ type: z.literal("order"), outlet: z.string().min(1) }).strict(),
    z
        .object({ type: z.literal("proof"), delivery: z.string().min(1) })
        .strict(),
    z
        .object({
            type: z.literal("expense"),
            trip: z.string().min(1).optional(),
        })
        .strict(),
    z
        .object({
            type: z.literal("attendance"),
            event: z.enum(["check_in", "check_out"]).optional(),
        })
        .strict(),
    ...["extra", "leave", "profile"].map((type) =>
        z.object({ type: z.literal(type) }).strict(),
    ),
]);
export const RouteSchema = z
    .object({
        page: z.enum(["home", "sales", "delivery", "hris", "more", "expenses"]),
        outlet: z.string().min(1).optional(),
        dialog: DialogSchema.optional(),
    })
    .strict();
function valid(value: unknown): value is Route {
    return RouteSchema.safeParse(value).success;
}
function hash(route: Route) {
    return `#${route.page}${route.outlet ? `/${encodeURIComponent(route.outlet)}` : ""}${route.dialog ? `/${route.dialog.type}` : ""}`;
}
export function useNavigation(
    scope: string,
    allowed: (route: Route) => boolean,
) {
    const initial = history.state?.field;
    const [route, setRoute] = useState<Route>(() =>
        initial?.scope === scope &&
        valid(initial.route) &&
        allowed(initial.route)
            ? initial.route
            : { page: "home" },
    );
    const ref = useRef(route),
        permitted = useRef(allowed);
    ref.current = route;
    permitted.current = allowed;
    useLayoutEffect(() => {
        history.replaceState(
            { field: { scope, route: ref.current, depth: 0 } },
            "",
            hash(ref.current),
        );
        const pop = () => {
            const field = history.state?.field;
            const next =
                field?.scope === scope &&
                valid(field.route) &&
                permitted.current(field.route)
                    ? field.route
                    : { page: "home" as const };
            ref.current = next;
            setRoute(next);
        };
        window.addEventListener("popstate", pop);
        return () => window.removeEventListener("popstate", pop);
    }, [scope]);
    function navigate(next: Route, replace = false) {
        if (!valid(next) || !permitted.current(next)) return;
        if (
            !replace &&
            JSON.stringify(next) === JSON.stringify(ref.current) &&
            !history.state?.layers?.length
        )
            return;
        const depth =
            history.state?.field?.scope === scope
                ? (history.state.field.depth ?? 0)
                : 0;
        history[replace ? "replaceState" : "pushState"](
            {
                field: {
                    scope,
                    route: next,
                    depth: replace ? depth : depth + 1,
                },
            },
            "",
            hash(next),
        );
        ref.current = next;
        setRoute(next);
    }
    return {
        route,
        navigate,
        dialog(value?: Dialog) {
            if (value) navigate({ ...ref.current, dialog: value });
            else if (ref.current.dialog) {
                // Close via Back so completed forms do not leave a duplicate parent
                // entry. The next submit still receives a fresh command UUID.
                if ((history.state?.field?.depth ?? 0) > 0) {
                    const parent = { ...ref.current, dialog: undefined };
                    history.replaceState(
                        {
                            ...history.state,
                            field: { ...history.state.field, route: parent },
                        },
                        "",
                        hash(parent),
                    );
                    history.back();
                } else navigate({ ...ref.current, dialog: undefined }, true);
            }
        },
    };
}

// Transient child layers (camera/search/DO) consume Back before the page route.
// No coordinates, media or form values are stored in browser history.
export function useBackLayer(enabled: boolean, close: () => void) {
    const latest = useRef(close);
    latest.current = close;
    useEffect(() => {
        if (!enabled) return;
        const id = crypto.randomUUID();
        const state = history.state ?? {};
        history.pushState(
            { ...state, layers: [...(state.layers ?? []), id] },
            "",
        );
        const pop = () => {
            if (!history.state?.layers?.includes(id)) latest.current();
        };
        window.addEventListener("popstate", pop);
        return () => {
            window.removeEventListener("popstate", pop);
            if (history.state?.layers?.at(-1) === id) history.back();
        };
    }, [enabled]);
}
