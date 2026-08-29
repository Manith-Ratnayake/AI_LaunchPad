import { transformQuery } from "./transformQuery";
import { createEmbedding } from "./createEmbedding";
import { vectorSearch } from "./vectorSearch";
import { rerankResults } from "./rerankResults";
import { buildContext } from "./buildContext";

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : String(error);
}

export async function runRagRetrieval({ message, chatModel }: any) {
  const query = message.parts.filter((part: any) => part.type === "text").map((part: any) => part.text).join(" ");

  let transformedQuery: string;
  try {
    transformedQuery = await transformQuery(query, chatModel);
  } catch (error) {
    throw new Error(`QUERY TRANSFORMATION FAILED: ${errorMessage(error)}`, { cause: error });
  }

  let embedding: number[];
  try {
    embedding = await createEmbedding(transformedQuery);
  } catch (error) {
    throw new Error(`EMBEDDING FAILED: ${errorMessage(error)}`, { cause: error });
  }

  let searchResults: any[];
  try {
    searchResults = await vectorSearch(embedding);
  } catch (error) {
    throw new Error(`OPENSEARCH FAILED: ${errorMessage(error)}`, { cause: error });
  }

  let rerankedResults: any[];
  try {
    rerankedResults = await rerankResults(transformedQuery, searchResults);
  } catch (error) {
    throw new Error(`RERANKING FAILED: ${errorMessage(error)}`, { cause: error });
  }

  const context = buildContext(rerankedResults);

  return {
    query,
    transformedQuery,
    rerankedResults,
    context,
  };
}
