export interface DeterministicZipEntry {
  readonly archivePath: string;
  readonly sourcePath: string;
  readonly mode: number;
}

export function writeDeterministicZip(
  outputPath: string,
  entries: readonly DeterministicZipEntry[],
  epoch: number,
): Promise<void>;
