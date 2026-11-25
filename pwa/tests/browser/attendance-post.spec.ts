import { MockProvider } from "../../src/data/mock";
import { expect, freshSnapshotMeta, test } from "./session-fixture";

test("Absensi pilot mengulangi UUID yang sama setelah respons hilang dan halaman dimuat ulang", async ({
    page,
}) => {
    const identity = await new MockProvider("sales", true).bootstrap();
    const businessDate = freshSnapshotMeta().businessDate;
    const office = {
        id: "1",
        name: "Kantor terverifikasi",
        latitude: 1.465,
        longitude: 124.833,
        radius: 100,
        coordinate_status: "verified",
    };
    await page.addInitScript(() =>
        localStorage.setItem("fmcg:running-mode", "live"),
    );
    await page.route("**/api/v1/me/bootstrap", (route) =>
        route.fulfill({
            json: {
                ...identity,
                businessDate,
                attendanceOffice: office,
                csrfToken: "fixture-command-csrf",
            },
        }),
    );
    const uploads: string[] = [];
    await page.route("**/api/v1/evidence", async (route) => {
        const form = route.request().postDataBuffer()!.toString();
        const encoded = form.match(/name="metadata"\r\n\r\n([^\r]+)/)?.[1];
        expect(encoded).toBeDefined();
        const metadata = JSON.parse(encoded!);
        expect(metadata.attendance_event).toBe("check_in");
        uploads.push(metadata.client_uuid);
        await route.fulfill({
            json: {
                ...metadata,
                user_id: identity.id,
                company_id: identity.companyId,
                office_id: office.id,
                received_at: metadata.device_recorded_at,
                distance_m: 0,
                radius_m: office.radius,
                original_sha256: "a".repeat(64),
                watermarked_sha256: "b".repeat(64),
                original_url: `/api/v1/evidence/${metadata.client_uuid}/original`,
                watermarked_url: `/api/v1/evidence/${metadata.client_uuid}/watermarked`,
            },
        });
    });
    const commands: unknown[] = [];
    await page.route("**/api/v1/sync/commands", async (route) => {
        const command = route.request().postDataJSON();
        expect(command.type).toBe("hris.attendance.capture");
        expect(command.client_uuid).toBe(uploads.at(-1));
        commands.push(command);
        if (commands.length === 1) {
            await route.fulfill({
                status: 503,
                json: { error: "unavailable" },
            });
            return;
        }
        await route.fulfill({
            json: {
                client_uuid: command.client_uuid,
                status: "accepted",
                message: "PWA attendance recorded.",
                reference: "hr.attendance:1",
            },
        });
    });

    await page.context().grantPermissions(["geolocation"]);
    await page.goto("./");
    await page
        .getByRole("button", { name: "Absen masuk", exact: true })
        .first()
        .click();
    const screen = page.getByRole("region", {
        name: "Absensi foto dan lokasi",
    });
    await screen.getByLabel("Alamat / nama lokasi").fill("Kantor Manado");
    await screen
        .getByRole("button", { name: "Ambil selfie", exact: true })
        .click();
    await page
        .getByLabel("Buka Kamera Perangkat")
        .setInputFiles("public/icon-192.png");
    await page
        .getByRole("button", { name: "Gunakan foto", exact: true })
        .click();
    const save = screen.getByRole("button", {
        name: "Absen masuk",
        exact: true,
    });
    await save.click();
    await expect(screen).toContainText("Status absensi belum terkonfirmasi");
    await expect(page.getByTestId("attendance-record")).toHaveCount(0);

    await page.reload();
    await expect(screen).toBeVisible();
    await expect(screen).toContainText(
        "Kirim ulang untuk memastikan status absensi di Odoo.",
    );
    await save.click();
    await expect(page.getByTestId("attendance-record")).toBeVisible();
    expect(uploads).toHaveLength(2);
    expect(uploads[0]).toBe(uploads[1]);
    expect(commands[0]).toEqual(commands[1]);
});
