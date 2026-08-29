import { transformQuery } from "./transformQuery";
import { createEmbedding } from "./createEmbedding";
import { vectorSearch } from "./vectorSearch";
import { rerankResults } from "./rerankResults";
import { buildContext } from "./buildContext";

export async function runRagRetrieval({ message, chatModel }: any) {
  const query = message.parts
    .filter((part: any) => part.type === "text")
    .map((part: any) => part.text)
    .join(" ");

  const transformedQuery = await transformQuery(query, chatModel);

  const embedding = await createEmbedding(transformedQuery);

  const searchResults = await vectorSearch(embedding);

  const rerankedResults = await rerankResults(transformedQuery, searchResults);

  const context = buildContext(rerankedResults);

  return {
    query,
    transformedQuery,
    rerankedResults,
    context,
  };
}