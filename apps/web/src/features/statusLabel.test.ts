import i18next from "i18next";
import { describe, expect, it } from "vitest";

import en from "../i18n/status.en.json";
import hi from "../i18n/status.hi.json";
import { statusLabel } from "./statusLabel";

const translations = i18next.createInstance();
void translations.init({ lng: "en", fallbackLng: "en", initImmediate: false,
  resources: { en: { translation: en }, hi: { translation: hi } } });

describe("statusLabel", () => {
  it("labels a known status in English and Hindi", () => {
    expect(statusLabel("ECR_SUBMITTED", translations.getFixedT("en"))).toBe("Return submitted");
    expect(statusLabel("ECR_SUBMITTED", translations.getFixedT("hi"))).toBe("विवरणी जमा की गई");
  });

  it("uses an existing journey label when the shared table has no entry", () => {
    const journey = i18next.createInstance();
    void journey.init({ lng: "en", initImmediate: false,
      resources: { en: { translation: { journeyB: { states: { JOURNEY_ONLY: "Journey label" } } } } } });
    expect(statusLabel("JOURNEY_ONLY", journey.t)).toBe("Journey label");
  });

  it("falls back silently to lower-case words", () => {
    expect(statusLabel("NEW_UNKNOWN_STATE", translations.t)).toBe("new unknown state");
    expect(statusLabel(null, translations.t)).toBe("—");
  });

  it("has matching English and Hindi code sets", () => {
    expect(Object.keys(en.status).sort()).toEqual(Object.keys(hi.status).sort());
  });
});
