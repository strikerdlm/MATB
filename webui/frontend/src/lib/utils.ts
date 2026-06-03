// Author: Dr Diego Malpica MD
/**
 * Utility functions for Mission Control - Flight Surgeon
 */

import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Merge Tailwind classes with clsx
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format ISO datetime string to human-readable format
 */
export function formatDateTime(
  isoString: string | null | undefined,
  options?: {
    includeTime?: boolean;
    includeSeconds?: boolean;
    relative?: boolean;
  }
): string {
  if (!isoString) return "N/A";

  const date = new Date(isoString);
  if (isNaN(date.getTime())) return "Invalid date";

  const {
    includeTime = true,
    includeSeconds = false,
    relative = false,
  } = options || {};

  // Relative time format
  if (relative) {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSec = Math.floor(diffMs / 1000);
    const diffMin = Math.floor(diffSec / 60);
    const diffHour = Math.floor(diffMin / 60);
    const diffDay = Math.floor(diffHour / 24);

    if (diffSec < 60) return "just now";
    if (diffMin < 60) return `${diffMin} minute${diffMin !== 1 ? "s" : ""} ago`;
    if (diffHour < 24)
      return `${diffHour} hour${diffHour !== 1 ? "s" : ""} ago`;
    if (diffDay < 7) return `${diffDay} day${diffDay !== 1 ? "s" : ""} ago`;
  }

  // Absolute format
  const dateStr = date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  if (!includeTime) return dateStr;

  const timeOptions: Intl.DateTimeFormatOptions = {
    hour: "2-digit",
    minute: "2-digit",
    ...(includeSeconds && { second: "2-digit" }),
  };

  const timeStr = date.toLocaleTimeString("en-US", timeOptions);

  return `${dateStr} ${timeStr}`;
}

/**
 * Format duration in minutes to human-readable string
 */
export function formatDuration(minutes: number): string {
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

/**
 * Format number with optional precision
 */
export function formatNumber(
  value: number | null | undefined,
  options?: {
    precision?: number;
    suffix?: string;
    fallback?: string;
  }
): string {
  if (value === null || value === undefined) {
    return options?.fallback || "N/A";
  }

  const { precision = 1, suffix = "" } = options || {};
  const formatted = value.toFixed(precision);

  return suffix ? `${formatted} ${suffix}` : formatted;
}

/**
 * Truncate text to max length with ellipsis
 */
export function truncate(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength - 3) + "...";
}

/**
 * Sleep for specified milliseconds (for testing/demos)
 */
export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Get initials from full name
 */
export function getInitials(name: string | null | undefined): string {
  if (!name) return "?";

  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0].charAt(0).toUpperCase();
  }

  return (
    parts[0].charAt(0).toUpperCase() + parts[parts.length - 1].charAt(0).toUpperCase()
  );
}

/**
 * Validate email format
 */
export function isValidEmail(email: string): boolean {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  return emailRegex.test(email);
}

/**
 * Generate random ID (client-side only, for UI keys)
 */
export function generateId(prefix: string = "id"): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
}

/**
 * Format date only (no time)
 */
export function formatDate(
  isoString: string | null | undefined
): string {
  if (!isoString) return "N/A";

  const date = new Date(isoString);
  if (isNaN(date.getTime())) return "Invalid date";

  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/**
 * Format value with unit
 */
export function formatWithUnit(
  value: number | null | undefined,
  unit: string,
  precision: number = 1
): string {
  if (value === null || value === undefined) return "N/A";
  return `${value.toFixed(precision)} ${unit}`;
}

/**
 * Capitalize first letter of string
 */
export function capitalize(text: string): string {
  if (!text) return "";
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/**
 * Get status color class
 */
export function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    draft: "text-muted-foreground",
    approved: "text-success",
    in_progress: "text-info",
    paused: "text-warning",
    completed: "text-success",
    cancelled: "text-danger",
    active: "text-success",
    inactive: "text-muted-foreground",
    pending: "text-warning",
    error: "text-danger",
  };
  return colors[status] || "text-muted-foreground";
}
