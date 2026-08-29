import { defaultProvider } from "@aws-sdk/credential-provider-node";
import { Client } from "@opensearch-project/opensearch";
import { AwsSigv4Signer } from "@opensearch-project/opensearch/aws";

function getClient() {
  const host = process.env.OPENSEARCH_HOST;

  if (!host) {
    throw new Error("OPENSEARCH_HOST is not set");
  }

  const credentialsProvider = defaultProvider();

  return new Client({
    ...AwsSigv4Signer({
      region: process.env.AWS_REGION || "us-east-1",
      service: "aoss",
      getCredentials: () => credentialsProvider(),
    }),
    node: host.startsWith("http") ? host : `https://${host}`,
  });
}

export async function vectorSearch(embedding: number[]) {
  const client = getClient();

  const response = await client.search({
    index: "annual-reports",
    body: {
      size: 20,
      query: {
        knn: {
          embedding: {
            vector: embedding,
            k: 20,
          },
        },
      },
    },
  });

  return response.body.hits.hits;
}