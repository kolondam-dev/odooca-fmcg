import { describe, expect, it } from "vitest";
import {
    computeWatermarkedDimensions,
    MAX_CANVAS_DIM,
} from "../src/components/CameraViewfinder";

describe("P2-5 Camera Viewfinder Watermark Dimension Clamping", () => {
    it("strictly clamps portrait 480x1200 to at most 1280px total height", () => {
        const dims = computeWatermarkedDimensions(480, 1200, false);
        expect(dims.totalHeight).toBeLessThanOrEqual(MAX_CANVAS_DIM);
        expect(dims.totalWidth).toBeLessThanOrEqual(MAX_CANVAS_DIM);
        expect(dims.bannerHeight).toBe(110);
        expect(dims.totalHeight).toBe(dims.targetHeight + dims.bannerHeight);
    });

    it("strictly clamps portrait 720x1280 to at most 1280px total height", () => {
        const dims = computeWatermarkedDimensions(720, 1280, false);
        expect(dims.totalHeight).toBeLessThanOrEqual(MAX_CANVAS_DIM);
        expect(dims.totalWidth).toBeLessThanOrEqual(MAX_CANVAS_DIM);
    });

    it("strictly clamps large phone photos 4000x3000 to at most 1280px", () => {
        const dims = computeWatermarkedDimensions(4000, 3000, false);
        expect(dims.totalHeight).toBeLessThanOrEqual(MAX_CANVAS_DIM);
        expect(dims.totalWidth).toBeLessThanOrEqual(MAX_CANVAS_DIM);
    });

    it("upscales small photos without exceeding 1280px", () => {
        const dims = computeWatermarkedDimensions(300, 400, false);
        expect(dims.totalHeight).toBeLessThanOrEqual(MAX_CANVAS_DIM);
        expect(dims.totalWidth).toBeLessThanOrEqual(MAX_CANVAS_DIM);
        expect(dims.targetWidth).toBe(800);
    });

    it("honors rawCapture mode without banner offset", () => {
        const dims = computeWatermarkedDimensions(480, 1200, true);
        expect(dims.bannerHeight).toBe(0);
        expect(dims.totalHeight).toBeLessThanOrEqual(MAX_CANVAS_DIM);
        expect(dims.totalWidth).toBeLessThanOrEqual(MAX_CANVAS_DIM);
    });
});
