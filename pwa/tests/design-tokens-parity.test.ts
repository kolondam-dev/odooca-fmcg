import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Pariti token desain: `src/ui/tokens.css` (runtime) harus sama dengan
// `design/tokens.json` (impor Figma / Tokens Studio). Tes ini menggagalkan CI
// bila salah satu sumber berubah sendiri (drift), mis. warna navbar.
const read = (rel: string) =>
    readFileSync(new URL(`../${rel}`, import.meta.url), "utf8");
const css = read("src/ui/tokens.css");
const jsonText = read("design/tokens.json");
const tokens: unknown = JSON.parse(jsonText);

type Node = { $value?: unknown } & Record<string, unknown>;

function cssVars(): Map<string, string> {
    const out = new Map<string, string>();
    for (const m of css.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) {
        out.set(m[1], m[2].replace(/\s+/g, " ").trim().toLowerCase());
    }
    return out;
}

function jsonValue(path: string): string {
    let node = tokens as Node | undefined;
    for (const part of path.split(".")) {
        node = node?.[part] as Node | undefined;
    }
    if (node?.$value === undefined) {
        throw new Error(`token JSON tidak ditemukan: ${path}`);
    }
    return String(node.$value).trim().toLowerCase();
}

const px = (path: string) => `${jsonValue(path)}px`;
const color = (path: string) => jsonValue(`color.${path}`);

// [variabel CSS, nilai dari JSON]
const PAIRS: [string, string][] = [
    ["--c-ink", color("base.ink")],
    ["--c-mute", color("base.mute")],
    ["--c-line", color("base.line")],
    ["--c-bd", color("base.border")],
    ["--c-bg", color("base.bg")],
    ["--c-surface", color("base.surface")],
    ["--c-pri", color("brand.primary")],
    ["--c-nav", color("brand.nav")],
    ["--c-nav-fg", color("brand.navFg")],
    ["--c-ok", color("status.ok")],
    ["--c-ok-bg", color("status.okBg")],
    ["--c-warn", color("status.warn")],
    ["--c-warn-bg", color("status.warnBg")],
    ["--c-bad", color("status.bad")],
    ["--c-bad-bg", color("status.badBg")],
    ["--c-info", color("status.info")],
    ["--c-info-bg", color("status.infoBg")],
    ["--c-neu", color("status.neutral")],
    ["--c-neu-bg", color("status.neutralBg")],
    ["--c-dis", color("status.disabled")],
    ["--c-dis-fg", color("status.disabledFg")],
    ["--c-badge", color("status.badge")],
    ["--c-online", color("status.online")],
    ["--r-sm", px("radius.sm")],
    ["--r-md", px("radius.md")],
    ["--r-lg", px("radius.lg")],
    ["--r-xl", px("radius.xl")],
    ["--r-pill", px("radius.pill")],
    ["--sp-1", px("spacing.1")],
    ["--sp-2", px("spacing.2")],
    ["--sp-3", px("spacing.3")],
    ["--sp-4", px("spacing.4")],
    ["--sp-5", px("spacing.5")],
    ["--sp-6", px("spacing.6")],
    ["--touch", px("size.touch")],
    ["--hdr-h", px("size.header")],
    ["--nav-h", px("size.nav")],
    ["--btn-lg", px("size.buttonLg")],
    ["--btn-md", px("size.buttonMd")],
    ["--btn-sm", px("size.buttonSm")],
    ["--field-h", px("size.field")],
];

// Variabel warna runtime yang sengaja tidak ada di JSON.
const RUNTIME_ONLY = new Set([
    "--c-scrim",
    "--c-bad-bd",
    "--c-cam",
    "--c-cam-box",
    "--c-map",
    "--c-map-green",
]);

describe("pariti design token CSS dan JSON", () => {
    const vars = cssVars();

    it.each(PAIRS)("%s sama dengan tokens.json", (name, expected) => {
        expect(vars.get(name), `${name} hilang`).toBe(expected);
    });

    it("navbar memakai #001A57 di kedua sumber (review PR #100)", () => {
        expect(vars.get("--c-nav")).toBe("#001a57");
        expect(color("brand.nav")).toBe("#001a57");
    });

    it("tidak ada variabel warna runtime baru tanpa padanan JSON", () => {
        const known = new Set([...PAIRS.map(([n]) => n), ...RUNTIME_ONLY]);
        const colorVars = [...vars.keys()].filter((n) => n.startsWith("--c-"));
        const orphan = colorVars.filter((n) => !known.has(n));
        expect(orphan).toEqual([]);
    });
});
