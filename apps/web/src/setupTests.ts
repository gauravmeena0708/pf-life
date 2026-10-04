import { expect } from "vitest";
import * as matchers from "vitest-axe/matchers.js";

expect.extend(matchers);

declare module "@vitest/expect" {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  interface Assertion<T = any> {
    toHaveNoViolations(): T;
  }
  interface AsymmetricMatchersContaining {
    toHaveNoViolations(): void;
  }
}
