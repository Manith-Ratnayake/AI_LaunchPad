export function buildContext(rerankedResults: any[]) {
  return rerankedResults
    .map((result, index) => {
      const source = result._source || {};

      return `
SOURCE ${index + 1}
Company: ${source.company || ""}
Year: ${source.year || ""}
Section: ${source.section || ""}
Subsection: ${source.subsection || ""}
Page: ${source.page_number || source.page || ""}
Content:
${source.source_text || source.search_text || ""}
`.trim();
    })
    .join("\n\n");
}