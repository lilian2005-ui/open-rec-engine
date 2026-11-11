/** Status as shown on screen: "draft_ready" -> "DRAFT READY" (same rule as the backend). */
export function displayStatus(value: string): string {
  return value.replace(/_/g, " ").toUpperCase();
}

/** Word count with the same rule as the backend (split on whitespace). */
export function countWords(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}