import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "./en.json";
import hi from "./hi.json";
import memberEn from "./member.en.json";
import memberHi from "./member.hi.json";

void i18n.use(initReactI18next).init({
  resources: { en: { translation: { ...en, ...memberEn } }, hi: { translation: { ...hi, ...memberHi } } },
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
