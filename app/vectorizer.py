import time
import json
import os
from typing import List, Dict, Any, Optional, Protocol
from abc import abstractmethod
import openai # Import openai library
import traceback # For logging exceptions

# Try importing requests, but make it optional
try:
    import requests
except ImportError:
    requests = None

from .models import SchemaModel
from config.settings import Settings # Import Settings class
from config.logging_config import get_logger # Import logger

logger = get_logger(__name__) # Get logger for this module

# Load configuration by instantiating Settings
try:
    settings = Settings()
except Exception as e:
    logger.critical(f"Failed to load settings in vectorizer.py: {e}", exc_info=True)
    # Depending on how critical config is, either raise, exit, or use defaults/dummies
    raise RuntimeError(f"Vectorizer configuration failed: {e}") from e

# Define data directory relative to this file's location (consistent with data_processor)
DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')

# --- Vectorizer Protocol --- #

class Vectorizer(Protocol):
    """Protocol defining the interface for different vectorization engines."""
    @abstractmethod
    def embed_texts(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Generates embeddings for a list of texts. Returns None for failed embeddings."""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Returns the dimension of the embeddings generated by this vectorizer."""
        ...

# --- OpenAI Vectorizer --- #

class OpenAIVectorizer(Vectorizer):
    """Vectorizer using the OpenAI Embeddings API."""
    DEFAULT_MODEL = "text-embedding-ada-002"
    DEFAULT_DIMENSION = 1536

    def __init__(self, api_key: str, base_url: Optional[str] = None, model: str = DEFAULT_MODEL):
        if not api_key:
             logger.error("OpenAI API key is required but not provided.")
             raise ValueError("OpenAI API key is required.")
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self._dimension = self.DEFAULT_DIMENSION # TODO: Potentially fetch dynamically
        logger.info(f"Initializing OpenAIVectorizer with model: {self.model}, dimension: {self._dimension}")

        # Configure OpenAI client instance
        try:
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=str(self.base_url) if self.base_url else None # Ensure base_url is string if provided
            )
            logger.debug("OpenAI client configured.")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
            raise


    def embed_texts(self, texts: List[str], batch_size: int = 100) -> List[Optional[List[float]]]:
        """Generates embeddings using OpenAI API with batching and basic retry."""
        all_embeddings = [None] * len(texts) # Initialize with None
        logger.info(f"Starting OpenAI embedding generation for {len(texts)} texts (batch size: {batch_size}).")

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            original_indices = list(range(i, i + len(batch_texts)))
            valid_texts_with_indices = [(idx, text) for idx, text in zip(original_indices, batch_texts) if isinstance(text, str) and text.strip()]

            if not valid_texts_with_indices:
                logger.debug(f"Batch {i//batch_size + 1}: No valid texts to embed, skipping.")
                continue

            batch_indices = [item[0] for item in valid_texts_with_indices]
            valid_batch_texts = [item[1] for item in valid_texts_with_indices]

            try:
                logger.debug(f"Sending batch {i//batch_size + 1} ({len(valid_batch_texts)} texts) to OpenAI API...")
                response = self.client.embeddings.create(
                    model=self.model,
                    input=valid_batch_texts
                )
                embeddings_data = response.data
                if len(embeddings_data) != len(valid_batch_texts):
                     logger.warning(f"Mismatch in returned embeddings count for OpenAI batch {i//batch_size + 1}. Expected {len(valid_batch_texts)}, got {len(embeddings_data)}.")
                     continue # Leave as None

                for j, embedding_item in enumerate(embeddings_data):
                    original_idx = batch_indices[j]
                    all_embeddings[original_idx] = embedding_item.embedding
                logger.debug(f"Received embeddings for batch {i//batch_size + 1}.")
                # Optional delay to prevent rate limiting
                # time.sleep(0.1)

            except openai.RateLimitError:
                logger.warning(f"OpenAI rate limit reached on batch {i//batch_size + 1}. Waiting 10s and retrying...")
                time.sleep(10)
                try:
                    logger.info(f"Retrying OpenAI batch {i//batch_size + 1}...")
                    response = self.client.embeddings.create(model=self.model, input=valid_batch_texts)
                    embeddings_data = response.data
                    if len(embeddings_data) != len(valid_batch_texts):
                         logger.warning(f"Mismatch on OpenAI retry for batch {i//batch_size + 1}.")
                         continue
                    for j, embedding_item in enumerate(embeddings_data):
                         original_idx = batch_indices[j]
                         all_embeddings[original_idx] = embedding_item.embedding
                    logger.info(f"Retry successful for OpenAI batch {i//batch_size + 1}.")
                except Exception as retry_e:
                    logger.error(f"OpenAI retry failed for batch {i//batch_size + 1}: {retry_e}", exc_info=True)

            except Exception as e:
                logger.error(f"Error calling OpenAI Embedding API for batch {i//batch_size + 1}: {e}", exc_info=True)
                # Nones are already in place for failed items in this batch

        successful_count = sum(1 for emb in all_embeddings if emb is not None)
        logger.info(f"OpenAI embedding generation finished. Successfully embedded {successful_count}/{len(texts)} texts.")
        return all_embeddings

    @property
    def dimension(self) -> int:
        return self._dimension

# --- BGE Vectorizer (Placeholder) --- #

class BGEVectorizer(Vectorizer):
    """Placeholder for BGE Vectorizer using a hypothetical API."""
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None, model: str = "bge-large-en"):
        if not base_url:
             logger.error("BGE Base URL is required but not configured.")
             raise ValueError("BGE Base URL is required for BGE Vectorizer.")
        if requests is None:
            logger.error("The 'requests' library is required for BGE Vectorizer but not installed.")
            raise ImportError("The 'requests' library is required for the BGE Vectorizer. Please install it: pip install requests")
        self.api_key = api_key
        self.base_url = str(base_url)
        self.model = model
        # TODO: Determine BGE dimension based on model or configuration
        self._dimension = 1024 # Example dimension for bge-large
        logger.info(f"Initializing BGEVectorizer (Placeholder) for model: {self.model} at {self.base_url}, dimension: {self._dimension}")
        logger.warning("BGEVectorizer API call logic needs implementation and testing.")

    def embed_texts(self, texts: List[str]) -> List[Optional[List[float]]]:
        """Placeholder: Implement actual BGE API call logic here."""
        logger.warning(f"BGE embed_texts called for {len(texts)} texts. Using placeholder logic.")
        all_embeddings = [None] * len(texts)
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        api_endpoint = f"{self.base_url}/embeddings" # Adjust if needed
        batch_size = 32 # Adjust based on API

        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            original_indices = list(range(i, i + len(batch_texts)))
            valid_texts_with_indices = [(idx, text) for idx, text in zip(original_indices, batch_texts) if isinstance(text, str) and text.strip()]

            if not valid_texts_with_indices:
                logger.debug(f"BGE Batch {i//batch_size + 1}: No valid texts, skipping.")
                continue

            batch_indices = [item[0] for item in valid_texts_with_indices]
            valid_batch_texts = [item[1] for item in valid_texts_with_indices]
            payload = {"input": valid_batch_texts, "model": self.model}

            try:
                logger.debug(f"Sending BGE batch {i//batch_size + 1} ({len(valid_batch_texts)} texts) to {api_endpoint}...")
                response = requests.post(api_endpoint, json=payload, headers=headers, timeout=30)
                response.raise_for_status()

                response_data = response.json().get('data', [])
                if len(response_data) != len(valid_batch_texts):
                    logger.warning(f"Mismatch in BGE response count for batch {i//batch_size + 1}.")
                    continue

                for j, item in enumerate(response_data):
                    embedding = item.get('embedding')
                    if isinstance(embedding, list):
                        original_idx = batch_indices[j]
                        all_embeddings[original_idx] = embedding
                    else:
                        logger.warning(f"Invalid embedding format received from BGE for batch {i//batch_size + 1}, item {j}.")

            except requests.exceptions.RequestException as e:
                logger.error(f"Error calling BGE API for batch {i//batch_size + 1}: {e}", exc_info=True)
            except json.JSONDecodeError:
                 logger.error(f"Error decoding BGE API response for batch {i//batch_size + 1}. Response: {response.text[:200]}...", exc_info=True)

        successful_count = sum(1 for emb in all_embeddings if emb is not None)
        logger.info(f"BGE embedding generation finished. Successfully embedded {successful_count}/{len(texts)} texts (using placeholder logic).")
        return all_embeddings


    @property
    def dimension(self) -> int:
        return self._dimension

# --- Factory Function --- #

def get_vectorizer(model_type: str) -> Vectorizer:
    """Factory function to get the appropriate vectorizer instance."""
    logger.info(f"Attempting to get vectorizer for type: {model_type}")
    if model_type.lower() == 'openai':
        try:
            return OpenAIVectorizer(
                api_key=settings.openai_api_key.get_secret_value(),
                base_url=str(settings.openai_base_url) if settings.openai_base_url else None
            )
        except ValueError as e:
             logger.error(f"Failed to initialize OpenAI Vectorizer: {e}")
             raise
    elif model_type.lower() == 'bge':
        if not settings.bge_base_url:
             logger.error("BGE_BASE_URL is not configured in .env, cannot initialize BGE vectorizer.")
             raise ValueError("BGE_BASE_URL is not configured in .env for BGE vectorizer.")
        try:
            return BGEVectorizer(
                api_key=settings.bge_api_key.get_secret_value() if settings.bge_api_key else None,
                base_url=str(settings.bge_base_url)
            )
        except (ImportError, ValueError) as e:
            logger.error(f"Failed to initialize BGE Vectorizer: {e}")
            raise
    else:
        logger.error(f"Unsupported vectorizer type requested: {model_type}")
        raise ValueError(f"Unsupported vectorizer type: '{model_type}'. Choose 'openai' or 'bge'.")

# --- Main Vectorization Logic --- #

def vectorize_jsonl_file(
    jsonl_file_path: str,
    schema: SchemaModel,
    model_type: str,
    text_field_name: str,
    vector_field_name: str
) -> str:
    """Reads a JSONL file, generates embeddings, and saves to a new JSONL file."""
    logger.info(f"Starting vectorization process for file '{jsonl_file_path}' using schema '{schema.name}'.")
    logger.info(f"Model: {model_type}, Text Field: '{text_field_name}', Vector Field: '{vector_field_name}'.")

    if not os.path.exists(jsonl_file_path):
        logger.error(f"Input JSONL file not found: {jsonl_file_path}")
        raise FileNotFoundError(f"Input JSONL file not found: {jsonl_file_path}")
    if not os.path.isfile(jsonl_file_path):
         logger.error(f"Input path is not a file: {jsonl_file_path}")
         raise ValueError(f"Input path is not a file: {jsonl_file_path}")

    # Validate schema fields
    schema_fields = {field['name']: field for field in schema.fields}
    if text_field_name not in schema_fields:
         msg = f"Text field '{text_field_name}' not found in schema '{schema.name}'."
         logger.error(msg)
         raise ValueError(msg)
    if vector_field_name not in schema_fields:
        msg = f"Vector field '{vector_field_name}' not found in schema '{schema.name}'."
        logger.error(msg)
        raise ValueError(msg)
    if not schema_fields[vector_field_name].get('is_vector'):
         msg = f"Field '{vector_field_name}' in schema '{schema.name}' is not defined as a vector field."
         logger.error(msg)
         raise ValueError(msg)
    if schema_fields[text_field_name].get('is_vector'):
         msg = f"Selected text field '{text_field_name}' cannot be a vector field itself."
         logger.error(msg)
         raise ValueError(msg)

    try:
        vectorizer = get_vectorizer(model_type)
    except (ValueError, ImportError) as e:
         logger.error(f"Failed to get vectorizer: {e}", exc_info=True)
         raise # Re-raise for UI to catch

    expected_dim = schema_fields[vector_field_name].get('dim')

    # Check dimension consistency
    if expected_dim and vectorizer.dimension != expected_dim:
        msg = f"Dimension mismatch: Vectorizer ({model_type}) dim {vectorizer.dimension} != Schema field '{vector_field_name}' dim {expected_dim}."
        logger.error(msg)
        raise ValueError(msg)
    elif not expected_dim:
        logger.warning(f"Dimension not specified for vector field '{vector_field_name}' in schema. Using vectorizer dimension: {vectorizer.dimension}")

    original_records = []
    texts_to_embed = []

    # Read the JSONL file
    logger.info(f"Reading JSONL file: {jsonl_file_path}")
    line_num = 0
    try:
        with open(jsonl_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line_num += 1
                if not line.strip():
                    continue
                record = json.loads(line)
                original_records.append(record)
                text = record.get(text_field_name)
                if isinstance(text, str) and text.strip():
                    texts_to_embed.append(text)
                else:
                    texts_to_embed.append(None) # Placeholder
                    logger.debug(f"Line {line_num}: No valid text found in field '{text_field_name}'.")
    except json.JSONDecodeError as e:
        msg = f"Error reading JSONL file {jsonl_file_path} at line {line_num}: Invalid JSON. {e}"
        logger.error(msg, exc_info=True)
        raise ValueError(msg) from e
    except Exception as e:
        msg = f"Error reading file {jsonl_file_path}: {e}"
        logger.error(msg, exc_info=True)
        raise RuntimeError(msg) from e

    if not any(texts_to_embed):
        logger.warning(f"No valid text found to embed in field '{text_field_name}' in {jsonl_file_path}. Output file will not contain new embeddings.")
        embeddings = [None] * len(original_records)
    else:
        valid_text_count = len([t for t in texts_to_embed if t is not None])
        logger.info(f"Generating embeddings for {valid_text_count} valid texts using {model_type}...")
        try:
             embeddings = vectorizer.embed_texts(texts_to_embed)
             logger.info("Embedding generation attempt finished.")
        except Exception as e:
             logger.error(f"Embedding generation failed: {e}", exc_info=True)
             raise RuntimeError(f"Embedding generation failed: {e}") from e

        if len(embeddings) != len(original_records):
             msg = f"Embedding count mismatch: Expected {len(original_records)}, Got {len(embeddings)}."
             logger.error(msg)
             raise RuntimeError(msg)

    # Update records with embeddings
    updated_records = []
    successful_embeddings = 0
    failed_embeddings = 0

    logger.info("Updating records with generated embeddings...")
    for i, record in enumerate(original_records):
        new_record = record.copy()
        generated_embedding = embeddings[i]

        if generated_embedding is not None:
            if expected_dim and len(generated_embedding) != expected_dim:
                 logger.warning(f"Record index {i}: Dimension mismatch (Expected {expected_dim}, got {len(generated_embedding)}). Skipping embedding update.")
                 new_record[vector_field_name] = record.get(vector_field_name)
                 failed_embeddings += 1
            else:
                 new_record[vector_field_name] = generated_embedding
                 successful_embeddings += 1
        else:
            new_record[vector_field_name] = record.get(vector_field_name)
            if texts_to_embed[i] is not None:
                failed_embeddings +=1
                logger.debug(f"Record index {i}: Failed to generate embedding (text was present).")

        updated_records.append(new_record)

    logger.info(f"Embedding update summary: {successful_embeddings} successful, {failed_embeddings} failed/skipped.")

    # Save to new file
    input_basename = os.path.basename(jsonl_file_path)
    name_part, ext = os.path.splitext(input_basename)
    output_filename = f"{name_part}_{model_type}_{vector_field_name}_embedded{ext}"
    output_path = os.path.join(DATA_DIR, output_filename)

    logger.info(f"Saving updated records to {output_path}")
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for record in updated_records:
                json.dump(record, f, ensure_ascii=False, default=lambda x: list(x) if hasattr(x, 'tolist') else x)
                f.write('\n')
        logger.info(f"Successfully saved data with updated embeddings to {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"Error saving embedded data to {output_path}: {e}", exc_info=True)
        raise