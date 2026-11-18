import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dir = join(__dirname, "../src/components");

/** K31/3B-18: tombol komponen memakai `Button` DS, bukan <button class="secondary|primary"> lama. */
describe("tombol gaya lama", () => {
    it("tidak ada <button class=secondary|primary> di komponen", () => {
        const offenders = readdirSync(dir)
            .filter((f) => f.endsWith(".tsx"))
            .filter((f) =>
                /<button\b[^>]*\bclass="(?:secondary|primary)"/s.test(
                    readFileSync(join(dir, f), "utf8"),
                ),
            );
        expect(offenders).toEqual([]);
    });
});
