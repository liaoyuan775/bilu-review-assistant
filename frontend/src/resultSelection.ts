export const toggleSelectedRuleId = (currentRuleId: string | null, clickedRuleId: string) =>
  currentRuleId === clickedRuleId ? null : clickedRuleId;
