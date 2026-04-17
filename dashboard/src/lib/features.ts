/** Must match backend `FEATURE_KEYS` order for stable UI. */
export const FEATURE_KEYS = [
  "typing_speed_wpm",
  "keystroke_interval_avg_ms",
  "keystroke_interval_std_ms",
  "backspace_rate",
  "error_rate",
  "pause_frequency",
  "burst_typing_ratio",
  "mouse_speed_avg",
  "mouse_speed_std",
  "click_rate_per_min",
  "double_click_rate",
  "scroll_events_per_min",
  "mouse_idle_ratio",
] as const;

export type FeatureKey = (typeof FEATURE_KEYS)[number];
