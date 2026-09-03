"use client";

import { ES } from "@/components/screen/strings_es";
import { useAppLocale } from "@/lib/i18n";

const EN = {
  common: {
    practice: "Practice",
    practiceDone: "Practice is complete. The scored test starts now.",
    ready: "Get ready…",
    continue: "Continue",
    start: "Start",
    subtestOf: (i: number, n: number) => `Test ${i} of ${n}`,
    done: "You have completed all tests. Thank you.",
    saving: "Saving results…",
  },
  simpleRt: {
    title: "Simple reaction time",
    instructions: "When the green circle appears, press the SPACE BAR as quickly as possible. Do not press before it appears.",
  },
  choiceRt: {
    title: "Choice reaction time",
    instructions: "An arrow will point LEFT or RIGHT. Press the corresponding arrow key (← or →) as quickly as possible.",
  },
  nback: {
    title: "Working memory (2-back)",
    instructions: "You will see letters one at a time. Press the SPACE BAR when the current letter is the SAME as the letter shown TWO positions earlier. Example: in C…G…C, the second C is a match.",
  },
  tracking: {
    title: "Mouse tracking",
    instructions: "A point will move around the screen. Keep the mouse pointer as close to the point as possible until time expires.",
  },
};

export function useScreenStrings() {
  const { locale } = useAppLocale();
  return locale === "en" ? EN : ES;
}
