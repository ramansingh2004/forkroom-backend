import type { Pool } from "pg";

export class YjsPersistence {
  public constructor(private readonly pool: Pool) {}

  public async fetch(documentName: string): Promise<Uint8Array | null> {
    const result = await this.pool.query<{ ydoc_state: Buffer | null }>(
      "SELECT ydoc_state FROM collaboration_documents WHERE document_name = $1",
      [documentName],
    );
    const state = result.rows[0]?.ydoc_state;
    return state ? new Uint8Array(state) : null;
  }

  public async store(documentName: string, state: Uint8Array): Promise<void> {
    const result = await this.pool.query(
      `UPDATE collaboration_documents
       SET ydoc_state = $2, state_version = state_version + 1, updated_at = now()
       WHERE document_name = $1`,
      [documentName, Buffer.from(state)],
    );
    if (result.rowCount !== 1) {
      throw new Error(`Unknown collaboration document: ${documentName}`);
    }
  }
}
