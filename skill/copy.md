Review the user-facing copy of this app, not the code. Copy means every
string a user can read or a screen reader can speak: titles, labels, buttons,
paywall or upsell text, empty states, errors, alerts, share sheets, and
accessibility-label strings. Edit this file to say where those strings live
in this repo (e.g. `src/components/`, `ios/<App>/Views`) and point at any
per-flow docs that already map screens to strings.

Review the whole app, and give the strings this branch adds or changes a
harder look; they are the newest and least settled.

Judge each string on: clarity to a first-time user; brevity for the space it
occupies (a card, a button, a row); one consistent name per concept across
screens; a consistent voice and casing (button verbs, Title Case vs sentence
case); tone on paywalls/upsells, which should be plain and confident, never
pushy or apologetic; errors that say what to do next; and accessibility
labels that read well when spoken.

Report each finding as a markdown bullet with: file:line, the current string
in quotes, the proposed string in quotes, one line on why, and a confidence
(high/medium/low). Group the bullets by screen. Then add a short 'Terms'
section listing any concept that is named more than one way, with the
file:line of each variant. Rank suggestions: an inconsistency or an unclear
string outranks a taste preference, and say which kind each is.

Do not modify any tracked files or commit. End with a 'Checks run' list
naming each command you ran, or 'none'.
