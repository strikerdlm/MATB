import { open, readFile, rm } from "node:fs/promises";
import { deflateRawSync } from "node:zlib";

const UTF8 = 0x0800;
const DEFLATE = 8;
const CRC_TABLE = Array.from({ length: 256 }, (_, value) => {
  let crc = value;
  for (let bit = 0; bit < 8; bit += 1) crc = (crc & 1) === 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1;
  return crc >>> 0;
});

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ byte) & 0xff];
  return (crc ^ 0xffffffff) >>> 0;
}

function dosTimestamp(epoch) {
  const date = new Date(epoch * 1000);
  if (!Number.isInteger(epoch) || date.getUTCFullYear() < 1980 || date.getUTCFullYear() > 2107) throw new Error("ZIP epoch must be an integer between 1980 and 2107");
  return {
    time: (date.getUTCHours() << 11) | (date.getUTCMinutes() << 5) | Math.floor(date.getUTCSeconds() / 2),
    date: ((date.getUTCFullYear() - 1980) << 9) | ((date.getUTCMonth() + 1) << 5) | date.getUTCDate(),
  };
}

function safeArchivePath(value) {
  if (typeof value !== "string" || value === "" || value.startsWith("/") || value.includes("\\")
    || value.split("/").some((part) => part === "" || part === "." || part === "..") || /^[A-Za-z]:/u.test(value)) {
    throw new Error(`unsafe ZIP archive path: ${String(value)}`);
  }
  const bytes = Buffer.from(value, "utf8");
  if (bytes.length > 0xffff) throw new Error(`ZIP archive path is too long: ${value}`);
  return bytes;
}

function localHeader(name, compressedSize, size, checksum, timestamp) {
  const header = Buffer.alloc(30);
  header.writeUInt32LE(0x04034b50, 0);
  header.writeUInt16LE(20, 4);
  header.writeUInt16LE(UTF8, 6);
  header.writeUInt16LE(DEFLATE, 8);
  header.writeUInt16LE(timestamp.time, 10);
  header.writeUInt16LE(timestamp.date, 12);
  header.writeUInt32LE(checksum, 14);
  header.writeUInt32LE(compressedSize, 18);
  header.writeUInt32LE(size, 22);
  header.writeUInt16LE(name.length, 26);
  return header;
}

function centralHeader(name, compressedSize, size, checksum, timestamp, mode, offset) {
  const header = Buffer.alloc(46);
  header.writeUInt32LE(0x02014b50, 0);
  header.writeUInt16LE((3 << 8) | 20, 4);
  header.writeUInt16LE(20, 6);
  header.writeUInt16LE(UTF8, 8);
  header.writeUInt16LE(DEFLATE, 10);
  header.writeUInt16LE(timestamp.time, 12);
  header.writeUInt16LE(timestamp.date, 14);
  header.writeUInt32LE(checksum, 16);
  header.writeUInt32LE(compressedSize, 20);
  header.writeUInt32LE(size, 24);
  header.writeUInt16LE(name.length, 28);
  header.writeUInt32LE(((0o100000 | mode) << 16) >>> 0, 38);
  header.writeUInt32LE(offset, 42);
  return header;
}

export async function writeDeterministicZip(outputPath, inputEntries, epoch) {
  if (!Array.isArray(inputEntries) || inputEntries.length === 0 || inputEntries.length > 0xffff) throw new Error("ZIP requires between 1 and 65535 regular-file entries");
  const entries = [...inputEntries].sort((left, right) => left.archivePath.localeCompare(right.archivePath));
  if (new Set(entries.map(({ archivePath }) => archivePath)).size !== entries.length) throw new Error("ZIP archive paths must be unique");
  const timestamp = dosTimestamp(epoch);
  const output = await open(outputPath, "wx", 0o644);
  const central = [];
  let offset = 0;
  try {
    for (const entry of entries) {
      const name = safeArchivePath(entry.archivePath);
      if (!Number.isInteger(entry.mode) || entry.mode < 0 || entry.mode > 0o777) throw new Error(`invalid ZIP mode: ${entry.archivePath}`);
      const body = await readFile(entry.sourcePath);
      const compressed = deflateRawSync(body, { level: 9 });
      if (body.length > 0xffffffff || compressed.length > 0xffffffff || offset > 0xffffffff) throw new Error("ZIP64-sized entries are not supported");
      const checksum = crc32(body);
      const local = localHeader(name, compressed.length, body.length, checksum, timestamp);
      await output.write(local);
      await output.write(name);
      await output.write(compressed);
      central.push(Buffer.concat([centralHeader(name, compressed.length, body.length, checksum, timestamp, entry.mode, offset), name]));
      offset += local.length + name.length + compressed.length;
    }
    const centralOffset = offset;
    for (const record of central) {
      await output.write(record);
      offset += record.length;
    }
    const centralSize = offset - centralOffset;
    if (offset > 0xffffffff || centralSize > 0xffffffff) throw new Error("ZIP64-sized archives are not supported");
    const end = Buffer.alloc(22);
    end.writeUInt32LE(0x06054b50, 0);
    end.writeUInt16LE(entries.length, 8);
    end.writeUInt16LE(entries.length, 10);
    end.writeUInt32LE(centralSize, 12);
    end.writeUInt32LE(centralOffset, 16);
    await output.write(end);
    await output.sync();
  } catch (error) {
    await output.close();
    await rm(outputPath, { force: true });
    throw error;
  }
  await output.close();
}
