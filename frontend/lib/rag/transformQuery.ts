import { generateText } from "ai";
import { getLanguageModel } from "@/lib/ai/providers";
import { queryTransformPrompt } from "@/lib/rag/queryTransformPrompt";

export async function transformQuery(query: string, chatModel: string) {
  const result = await generateText({
    model: getLanguageModel(chatModel),
    system: queryTransformPrompt,
    prompt: query,
  });

  return result.text.trim();
}