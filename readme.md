# AI Interior Design Platform

## Goal

Build an AI-powered interior design platform that recommends products based on user input and creates an efficient RAG (Retrieval-Augmented Generation) pipeline.

## Current Work

- Data ingestion and schema design for interior design assets and product information.
- Embeddings generation and database schema setup for retrieval and semantic search.
- Initial caching and fetcher utilities to support dataset loading and preprocessing.
- Parsing and tagging utilities for product dimensions, style, and catalog metadata.

## Future Steps

- Create the **retrieval layer** to serve relevant content for user queries.
- Attach the responding LLM to generate answers and recommendations from retrieved context.
- Implement context management to preserve conversation state and ensure coherent responses.
- Develop a frontend to enable intuitive user interaction with the platform.
