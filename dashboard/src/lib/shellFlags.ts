/**
 * Client-side heuristics to flag potentially harmful shell commands.
 * Returns a label string if suspicious, null if clean.
 */

const RULES: Array<{ pattern: RegExp; label: string }> = [
  { pattern: /rm\s+(-\w*r\w*f|-\w*f\w*r|--force|--recursive)/i, label: "destructive delete" },
  { pattern: /\brm\b.*\*/, label: "wildcard delete" },
  { pattern: /\bdd\b/, label: "disk write" },
  { pattern: /mkfs|fdisk|diskutil\s+erase/i, label: "disk format" },
  { pattern: />\s*\/dev\/(sd|hd|nvme|disk)/i, label: "raw device write" },
  { pattern: /\bsudo\b/, label: "sudo" },
  { pattern: /\bsu\b\s/, label: "su" },
  { pattern: /chmod\s+[0-7]*7[0-7]{2}|chmod\s+.*777/i, label: "permissive chmod" },
  { pattern: /curl.*(sh|bash|zsh|python|perl|ruby)\b/i, label: "remote exec" },
  { pattern: /wget.*(sh|bash|zsh|python|perl|ruby)\b/i, label: "remote exec" },
  { pattern: /\|\s*(ba|z)?sh\b/i, label: "pipe to shell" },
  { pattern: /\bnc\b|\bnetcat\b/i, label: "netcat" },
  { pattern: /\bnmap\b/i, label: "port scan" },
  { pattern: /\bwhoami\b|\bid\b/, label: "recon" },
  { pattern: /\/etc\/passwd|\/etc\/shadow/i, label: "credential file" },
  { pattern: /\bkill\b\s+-9|-KILL|-SIGKILL/i, label: "force kill" },
  { pattern: /pkill|killall/i, label: "mass kill" },
  { pattern: /\bpython[23]?\s+-c\b|\bperl\s+-e\b|\bruby\s+-e\b/i, label: "inline exec" },
  { pattern: /base64\s+--?d|base64\s+--decode/i, label: "base64 decode" },
  { pattern: /\bexfil|exfiltrat/i, label: "exfiltration keyword" },
  { pattern: /\bhistory\s*-c\b|unset\s+HISTFILE/i, label: "history tampering" },
  { pattern: /ssh\s+.*-R\s|ssh\s+.*-L\s/i, label: "ssh tunnel" },
];

export function flagCommand(command: string): string | null {
  for (const rule of RULES) {
    if (rule.pattern.test(command)) return rule.label;
  }
  return null;
}
