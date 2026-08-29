export async function rerankResults(query: string, searchResults: any[]) {
  const apiKey = process.env.DASHSCOPE_API_KEY;

  if (!apiKey) {
    throw new Error("DASHSCOPE_API_KEY is not set");
  }

  const documents = searchResults.map((result) => result._source?.search_text || result._source?.source_text || "");

  const response = await fetch("https://dashscope-intl.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: "qwen3-rerank",
      query,
      documents,
      top_n: 5,
    }),
  });

  if (!response.ok) {
    throw new Error(`Rerank failed: ${response.status} ${await response.text()}`);
  }

  const data = await response.json();
  const results = data.results || data.output?.results || [];

  return results.map((result: any) => ({
    ...searchResults[result.index],
    rerankScore: result.relevance_score,
  }));
}