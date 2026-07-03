export type PromptParts = {
  character: string;
  action: string;
  setting: string;
  twist: string;
};

export const promptPartOptions: Record<keyof PromptParts, string[]> = {
  character: ["a giraffe", "a sleepy astronaut", "a robot", "a tiny wizard", "a jealous cactus", "a dolphin", "a moon rock"],
  action: ["teaching", "babysitting", "arguing with", "cooking for", "juggling", "rescuing", "interviewing"],
  setting: ["on the moon", "inside a courtroom", "in a piano shop", "at a beach cafe", "in a dragon kitchen", "underwater"],
  twist: ["during a talent show", "while everyone is confused", "with dramatic lighting", "using only spoons", "in total silence"],
};

export const promptPartLabels: Record<keyof PromptParts, string> = {
  character: "Character or object",
  action: "Action",
  setting: "Setting",
  twist: "Twist",
};

export const promptPartPlaceholders: Record<keyof PromptParts, string> = {
  character: "a giraffe, a toaster, a moon rock",
  action: "teaching, stealing, babysitting",
  setting: "inside a piano shop",
  twist: "during a talent show",
};

const promptOrder: (keyof PromptParts)[] = ["character", "action", "setting", "twist"];

function pick(items: string[]) {
  return items[Math.floor(Math.random() * items.length)];
}

export function randomPromptParts(): PromptParts {
  return {
    character: pick(promptPartOptions.character),
    action: pick(promptPartOptions.action),
    setting: pick(promptPartOptions.setting),
    twist: pick(promptPartOptions.twist),
  };
}

export function randomizePromptPart(parts: PromptParts, key: keyof PromptParts): PromptParts {
  return { ...parts, [key]: pick(promptPartOptions[key]) };
}

export function buildPrompt(parts: PromptParts) {
  return promptOrder.map((key) => parts[key].trim()).filter(Boolean).join(" ");
}

export function randomPrompt() {
  return buildPrompt(randomPromptParts());
}
