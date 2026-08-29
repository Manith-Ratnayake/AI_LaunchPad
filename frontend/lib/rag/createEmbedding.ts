import OpenAI from "openai";

const qwenClient = new OpenAI({
  apiKey: process.env.DASHSCOPE_API_KEY,
  baseURL: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
});

export async function createEmbedding(query: string) {
  const response = await qwenClient.embeddings.create({
    model: "text-embedding-v4",
    input: query,
    dimensions: 1024,
  });

  return response.data[0].embedding;
}