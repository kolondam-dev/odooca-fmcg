/** Batas akurasi GPS untuk absen dan check-in toko (DS Status_gps). */
export const GPS_ACCURACY_LIMIT_M = 30;

/**
 * Akurasi di atas batas hanya berlaku di mode live dan untuk titik yang
 * divalidasi (bukan demo, bukan outlet `demo_unrestricted`).
 */
export function accuracyExceeded(
    accuracy: number,
    opts: { demo: boolean; unrestricted?: boolean },
): boolean {
    return (
        !opts.demo &&
        !opts.unrestricted &&
        Number.isFinite(accuracy) &&
        accuracy > GPS_ACCURACY_LIMIT_M
    );
}
