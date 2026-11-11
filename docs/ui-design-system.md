# Studio interface conventions

The shared theme lives at the start of `frontend/style.css` in the `--ui-*` variables. Change these values to adjust all standard controls together.

- `button.primary`: main action, amber background.
- `button.secondary`: secondary action, quiet grey background and border.
- `button.outline`: quiet outlined action, one shared grey hover and border for channel settings, Studio settings and New episode. Component rules only set size and placement.
- `button.danger`: destructive action.
- Standard action buttons use 13 px text, 18 px icons, 8 by 12 px padding and pill corners.
- Text fields use the shared field radius, colour and border. Textareas keep a separate content height.
- Dialogs share the dark surface and corner radius. Close controls have the same size.
- Special controls such as playback, timeline handles, image cards and segmented navigation retain their functional geometry.
- Keep component rules for layout. Avoid overriding action typography and corner radius in individual dialogs.
- Use the header cross for closing. Keep a cancel button when it cancels actual running work.
- `[hidden]` must override component display rules.
- The shared modal handler ignores disabled buttons, locks the clicked action and prevents duplicate submissions. Action callbacks must not reject that already locked button through another `if (button.disabled)` guard. An optional `enabled()` callback restores the correct validated state after an async action. Exercise export and audio-speed actions through this wrapper in regression checks.
- Every modal open/close advances `state.modalGeneration`. Async dialog reads and completion callbacks must retain their own generation and project/navigation identity; a late response cannot reopen, overwrite or close another dialog. Unexpected action failures are shown through the shared status message and release the clicked button.
- Channel hover, focus and selection paint the same outer row. Keep the inner channel button transparent so the highlight bounds remain identical with or without an activity spinner.
- Active export cards show «Експорт» and the total percentage beside it. Keep internal frame counts out of the card status.
- Channel settings place «Прев’ю» and «Монтаж» in the main navigation group with script, appearance and «Озвучка». Director rules live in «Монтаж».

## Visual verification on 10 November 2026

Checked the channel overview, all seven channel settings sections, global settings, new episode title and reference modes, project-bound opening cards, preview creation and cloning, language picker and export settings. Preview cloning was checked at 1470, 800 and 390 px widths. No paid generation, export or credential copying was used for visual QA.

Project-bound opening cards were additionally checked in a temporary read-only server using existing saved hooks. Integration tests cover selecting a hook once, loading the full saved script, retries without duplicate request receipts, stopping polling and ignoring responses after project navigation.

These checks cover shared controls and the listed views. Provider-specific success screens and every nested error state were not exercised live.

## Verification on 11 November 2026

Visited all nine settings sections on the live Studio without changing channel choices. None overflowed horizontally or enabled Save merely through navigation. Opened the completed 95-frame montage and verified the existing source, creation summary, preview and timeline. The former transition toolbar is hidden in the current combined workspace; its compatibility handler and shared library navigation are checked in a JavaScript regression test. No paid generation or real-project export was started for this audit.

## Additional verification on 11 November 2026

The three outlined overview controls share actual computed hover background, border and pill corners. All nine channel settings panels were checked at 1470, 780 and 390 px. The New episode scroll gutter now follows the dialog padding on narrow screens, retaining space for the action glow. The isolated browser blocked mutations and paid work.
