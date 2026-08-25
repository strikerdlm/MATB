export interface PlatformInventoryVerification {
  readonly valid: boolean;
  readonly missing: readonly string[];
  readonly unexpected: readonly string[];
  readonly mismatched: readonly string[];
}

export function verifyPlatformInventory(root: string): Promise<PlatformInventoryVerification>;
