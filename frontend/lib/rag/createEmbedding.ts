import { alibaba, type AlibabaEmbeddingModelOptions } from "@ai-sdk/alibaba";
import { embed } from "ai";

export async function createEmbedding(query: string) {
  const { embedding } = await embed({
    model: alibaba.embedding("text-embedding-v4"),
    value: query,
    providerOptions: {
      alibaba: {
        textType: "query",
        dimension: 1024,
        outputType: "dense",
      } satisfies AlibabaEmbeddingModelOptions,
    },
  });

  return embedding;
}