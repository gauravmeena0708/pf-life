import type { ApiError } from "../../api/client";
import type { FieldError } from "./ErrorSummary";

export function extractErrors(cause: unknown): FieldError[] {
  if (!cause) return [];
  const apiErr = cause as ApiError;
  if (apiErr.problem) {
    if (Array.isArray(apiErr.problem.errors) && apiErr.problem.errors.length > 0) {
      return apiErr.problem.errors.map((e) => {
        if (typeof e === "string") return { message: e };
        return { field: e.field, message: e.message || e.msg || apiErr.problem.title };
      });
    }
    const msg = apiErr.problem.detail || apiErr.problem.title;
    return [{ message: msg }];
  }
  if (cause instanceof Error) {
    return [{ message: cause.message }];
  }
  return [{ message: String(cause) }];
}
