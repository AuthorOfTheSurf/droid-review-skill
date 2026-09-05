Review the user-facing copy of this iOS word game, not the code. Copy means
every string a player can read or VoiceOver can speak: titles, card labels,
buttons, paywall and celebration text, empty states, errors, alerts, share
sheets, and accessibilityLabel strings. Find it in ios/TworDuel/Views (and the
Engine files that produce display strings); structural search helps:
  ast-grep run -l swift -p 'Text("$S")' ios/TworDuel
  ast-grep run -l swift -p 'Text($S)' ios/TworDuel
  grep -rn '"' ios/TworDuel/Views --include=*.swift
docs/features/ has one map per flow, so you know which screen each string
sits on and what the player has just done when they read it.
Review the whole app, and give the strings this branch adds or changes a
harder look; they are the newest and least settled.
Judge each string on: clarity to a first-time player; brevity for the space
it occupies (a card, a button, a row); one consistent name per concept across
screens (the unlock product, pass packs, seats, Friends & Family, Word of the
Day); a consistent voice and casing (button verbs, Title Case vs sentence
case); tone on the paywall, which should be plain and confident, never pushy
or apologetic; errors that say what to do next; and accessibility labels that
read well when spoken.
Report each finding as a markdown bullet with: file:line, the current string
in quotes, the proposed string in quotes, one line on why, and a confidence
(high/medium/low). Group the bullets by screen. Then add a short
'Terms' section listing any concept that is named more than one way, with
the file:line of each variant. Rank suggestions: an inconsistency or an
unclear string outranks a taste preference, and say which kind each is.
You may run ios/scenario.sh <preset> and agent-device to read a screen's
labels in context (identifiers and values, never screenshots), but reading
the source is enough for most of this. Do not modify any tracked files or
commit. End with a 'Checks run' list naming each command you ran, or 'none'.
