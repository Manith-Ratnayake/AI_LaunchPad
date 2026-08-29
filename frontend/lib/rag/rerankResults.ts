const RERANK_URL = "https://dashscope-intl.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank";
const RERANK_MODEL = "qwen3-rerank";
const MAX_DOCUMENTS = 500;
const DEFAULT_TOP_N = 5;

type RerankAttempt = {
  ok: boolean;
  status: number;
  statusText: string;
  headers: Record<string, string>;
  raw: string;
  data: any;
};

function getDocument(result: any) {
  const searchText = result?._source?.search_text;
  if (typeof searchText === "string" && searchText.trim()) return { text: searchText.trim(), field: "search_text" };

  const sourceText = result?._source?.source_text;
  if (typeof sourceText === "string" && sourceText.trim()) return { text: sourceText.trim(), field: "source_text" };

  return { text: "", field: "none" };
}

async function callReranker(apiKey: string, format: "nested" | "flat", body: any): Promise<RerankAttempt> {
  console.log(`[RERANK] ===== REQUEST START (${format}) =====`);
  console.log("[RERANK] Endpoint:", RERANK_URL);
  console.log("[RERANK] Model:", RERANK_MODEL);
  console.log("[RERANK] Request format:", format);
  console.log("[RERANK] Request body:", JSON.stringify(body, null, 2));

  const startedAt = Date.now();

  let response: Response;
  try {
    response = await fetch(RERANK_URL, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  } catch (error: any) {
    console.error("[RERANK] NETWORK/FETCH ERROR:", {
      name: error?.name,
      message: error?.message,
      cause: error?.cause,
      stack: error?.stack,
    });
    throw new Error(`Rerank network request failed: ${error?.message || String(error)}`);
  }

  const raw = await response.text();
  const headers = Object.fromEntries(response.headers.entries());

  let data: any = null;
  try {
    data = raw ? JSON.parse(raw) : null;
  } catch (error: any) {
    console.error("[RERANK] RESPONSE JSON PARSE ERROR:", {
      message: error?.message,
      rawResponse: raw,
    });
  }

  console.log("[RERANK] HTTP status:", response.status, response.statusText);
  console.log("[RERANK] Duration ms:", Date.now() - startedAt);
  console.log("[RERANK] Response headers:", headers);
  console.log("[RERANK] Raw response:", raw);
  console.log("[RERANK] Parsed response:", data ? JSON.stringify(data, null, 2) : null);
  console.log(`[RERANK] ===== REQUEST END (${format}) =====`);

  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    headers,
    raw,
    data,
  };
}

export async function rerankResults(query: string, searchResults: any[]) {
  const apiKey = process.env.DASHSCOPE_API_KEY;

  console.log("[RERANK] ===== INPUT DIAGNOSTICS =====");
  console.log("[RERANK] DASHSCOPE_API_KEY present:", Boolean(apiKey));
  console.log("[RERANK] DASHSCOPE_API_KEY length:", apiKey?.length ?? 0);
  console.log("[RERANK] Query type:", typeof query);
  console.log("[RERANK] Query length:", typeof query === "string" ? query.length : 0);
  console.log("[RERANK] Query:", query);
  console.log("[RERANK] searchResults is array:", Array.isArray(searchResults));
  console.log("[RERANK] searchResults count:", Array.isArray(searchResults) ? searchResults.length : 0);

  if (!apiKey) {
    throw new Error("DASHSCOPE_API_KEY is not set");
  }

  if (typeof query !== "string" || !query.trim()) {
    throw new Error("Reranking failed because query is empty");
  }

  if (!Array.isArray(searchResults) || searchResults.length === 0) {
    throw new Error("Reranking failed because searchResults is empty");
  }

  const candidateDetails = searchResults.map((result, originalIndex) => {
    const document = getDocument(result);

    return {
      originalIndex,
      document: document.text,
      field: document.field,
      documentLength: document.text.length,
      resultKeys: result && typeof result === "object" ? Object.keys(result) : [],
      sourceKeys: result?._source && typeof result._source === "object" ? Object.keys(result._source) : [],
      opensearchScore: result?._score,
      documentId: result?._id,
    };
  });

  console.log("[RERANK] Candidate diagnostics:", JSON.stringify(candidateDetails.map((candidate) => ({
    originalIndex: candidate.originalIndex,
    field: candidate.field,
    documentLength: candidate.documentLength,
    documentPreview: candidate.document.slice(0, 500),
    resultKeys: candidate.resultKeys,
    sourceKeys: candidate.sourceKeys,
    opensearchScore: candidate.opensearchScore,
    documentId: candidate.documentId,
  })), null, 2));

  const candidates = candidateDetails.filter((candidate) => candidate.document.length > 0).slice(0, MAX_DOCUMENTS);

  console.log("[RERANK] Valid document count:", candidates.length);
  console.log("[RERANK] Empty document count:", candidateDetails.length - candidateDetails.filter((candidate) => candidate.document.length > 0).length);
  console.log("[RERANK] Documents limited to:", MAX_DOCUMENTS);

  if (candidates.length === 0) {
    throw new Error("Reranking failed because none of the OpenSearch results contain _source.search_text or _source.source_text");
  }

  const cleanQuery = query.trim();
  const documents = candidates.map((candidate) => candidate.document);
  const topN = Math.min(DEFAULT_TOP_N, documents.length);

  console.log("[RERANK] Final query:", cleanQuery);
  console.log("[RERANK] Final document count:", documents.length);
  console.log("[RERANK] top_n:", topN);
  console.log("[RERANK] Document lengths:", documents.map((document) => document.length));

  /*
   * Your current DashScope endpoint returned:
   * "Field required: input.query & Field required: input.documents"
   *
   * Therefore this code tries the nested DashScope request format first.
   * If the endpoint rejects that format, it automatically retries the flat
   * qwen3-rerank format as a compatibility fallback.
   */
  const nestedBody = {
    model: RERANK_MODEL,
    input: {
      query: cleanQuery,
      documents,
    },
    parameters: {
      top_n: topN,
    },
  };

  let attempt = await callReranker(apiKey, "nested", nestedBody);

  if (!attempt.ok) {
    console.warn("[RERANK] Nested format failed. Retrying once with flat qwen3-rerank format.");

    const flatBody = {
      model: RERANK_MODEL,
      query: cleanQuery,
      documents,
      top_n: topN,
    };

    const flatAttempt = await callReranker(apiKey, "flat", flatBody);

    if (!flatAttempt.ok) {
      throw new Error(
        `Rerank failed in both request formats. Nested: ${attempt.status} ${attempt.raw} | Flat: ${flatAttempt.status} ${flatAttempt.raw}`,
      );
    }

    attempt = flatAttempt;
  }

  const data = attempt.data;

  if (!data || typeof data !== "object") {
    throw new Error(`Rerank returned a non-JSON or empty response: ${attempt.raw}`);
  }

  const results = Array.isArray(data.results) ? data.results : Array.isArray(data.output?.results) ? data.output.results : [];

  console.log("[RERANK] Response request_id:", data.request_id ?? data.requestId ?? null);
  console.log("[RERANK] Response usage:", data.usage ?? null);
  console.log("[RERANK] Results location:", Array.isArray(data.results) ? "data.results" : Array.isArray(data.output?.results) ? "data.output.results" : "not found");
  console.log("[RERANK] Result count:", results.length);
  console.log("[RERANK] Raw rerank results:", JSON.stringify(results, null, 2));

  if (results.length === 0) {
    throw new Error(`Rerank succeeded with HTTP ${attempt.status}, but no results array was found. Response: ${attempt.raw}`);
  }

  const mappedResults = results.map((result: any, rerankedPosition: number) => {
    const candidateIndex = Number(result?.index);

    if (!Number.isInteger(candidateIndex) || candidateIndex < 0 || candidateIndex >= candidates.length) {
      console.error("[RERANK] INVALID RESULT INDEX:", {
        rerankedPosition,
        returnedIndex: result?.index,
        candidateCount: candidates.length,
        result,
      });
      throw new Error(`Rerank returned invalid document index: ${result?.index}`);
    }

    const candidate = candidates[candidateIndex];
    const originalResult = searchResults[candidate.originalIndex];

    return {
      ...originalResult,
      rerankScore: result?.relevance_score ?? result?.relevanceScore ?? result?.score ?? null,
    };
  });

  console.log("[RERANK] Final mapped results:", JSON.stringify(mappedResults.map((result: any, index: number) => ({
    rank: index + 1,
    id: result?._id,
    opensearchScore: result?._score,
    rerankScore: result?.rerankScore,
    sourceKeys: result?._source && typeof result._source === "object" ? Object.keys(result._source) : [],
  })), null, 2));
  console.log("[RERANK] ===== RERANK COMPLETE =====");

  return mappedResults;
}
