/**
 * Generic error reporting utility.
 * Logs errors to the console. Extend this to integrate with a
 * monitoring service (e.g. Sentry, Datadog) when needed.
 */
export function reportError(
  error: unknown,
  context: Record<string, unknown> = {},
): void {
  console.error("[TouchWood] Error caught:", error, context);
}
