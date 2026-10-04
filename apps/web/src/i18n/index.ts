import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import hi from "./hi.json";
import memberEn from "./member.en.json";
import memberHi from "./member.hi.json";
import statusEn from "./status.en.json";
import statusHi from "./status.hi.json";
import journeyEn from "./journey.en.json";
import journeyHi from "./journey.hi.json";
import queueEn from "./queue.en.json";
import queueHi from "./queue.hi.json";
import caseEn from "./case.en.json";
import caseHi from "./case.hi.json";

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: { ...en, ...memberEn, ...statusEn, ...journeyEn, ...queueEn, ...caseEn } },
    hi: { translation: { ...hi, ...memberHi, ...statusHi, ...journeyHi, ...queueHi, ...caseHi } },
  },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
