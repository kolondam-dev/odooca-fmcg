import { inflateRawSync } from "node:zlib";

const ZIP_EOCD = 0x06054b50;
const ZIP_CENTRAL = 0x02014b50;
const ZIP_LOCAL = 0x04034b50;

/**
 * Read one file out of a ZIP container.
 *
 * The export is built by xlsxwriter, so it is a deflated ZIP. Parsing the end
 * of central directory and the selected entry keeps the smoke test dependent
 * only on Node's zlib: no archive library and no external process.
 */
export function readZipEntry(archive: Buffer, name: string): Buffer {
    if (archive.length < 22) throw new Error("file is too short to be a ZIP");

    let eocd = -1;
    const lowest = Math.max(0, archive.length - 22 - 0xffff);
    for (let offset = archive.length - 22; offset >= lowest; offset -= 1) {
        if (archive.readUInt32LE(offset) === ZIP_EOCD) {
            eocd = offset;
            break;
        }
    }
    if (eocd < 0) {
        throw new Error("ZIP end-of-central-directory record not found");
    }

    const entries = archive.readUInt16LE(eocd + 10);
    let cursor = archive.readUInt32LE(eocd + 16);
    for (let index = 0; index < entries; index += 1) {
        if (archive.readUInt32LE(cursor) !== ZIP_CENTRAL) {
            throw new Error(
                `ZIP central directory entry ${index} is malformed`,
            );
        }
        const method = archive.readUInt16LE(cursor + 10);
        const compressedSize = archive.readUInt32LE(cursor + 20);
        const nameLength = archive.readUInt16LE(cursor + 28);
        const extraLength = archive.readUInt16LE(cursor + 30);
        const commentLength = archive.readUInt16LE(cursor + 32);
        const localOffset = archive.readUInt32LE(cursor + 42);
        const entryName = archive
            .subarray(cursor + 46, cursor + 46 + nameLength)
            .toString("utf8");
        if (entryName === name) {
            if (archive.readUInt32LE(localOffset) !== ZIP_LOCAL) {
                throw new Error(`ZIP local header for ${name} is malformed`);
            }
            const localNameLength = archive.readUInt16LE(localOffset + 26);
            const localExtraLength = archive.readUInt16LE(localOffset + 28);
            const start = localOffset + 30 + localNameLength + localExtraLength;
            const body = archive.subarray(start, start + compressedSize);
            if (method === 0) return Buffer.from(body);
            if (method === 8) return inflateRawSync(body);
            throw new Error(
                `ZIP entry ${name} uses unsupported method ${method}`,
            );
        }
        cursor += 46 + nameLength + extraLength + commentLength;
    }
    throw new Error(`ZIP entry ${name} not found`);
}
