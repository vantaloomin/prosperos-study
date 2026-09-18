export interface PassageReader { branchId: string; show: (messageId: string) => boolean }

/** Deliver an explicit source-reading request to its own mounted branch only. */
export class PassageNavigation {
  private reader: PassageReader | null = null
  private pending: { branchId: string; messageId: string } | null = null

  connect = (reader: PassageReader | null) => {
    this.reader = reader
    if (!reader) return
    const pending = this.pending
    this.pending = null
    if (pending?.branchId === reader.branchId) reader.show(pending.messageId)
  }

  request(branchId: string, messageId: string) {
    if (this.reader?.branchId === branchId) {
      this.pending = null
      return this.reader.show(messageId)
    }
    this.pending = { branchId, messageId }
    return true
  }
}
