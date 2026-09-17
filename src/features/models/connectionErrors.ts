export function connectionError(failure: unknown): string {
  if (!(failure instanceof Error)) return 'The connection test failed. Check that Prospero’s Study and your model server are both running.'
  const status = 'status' in failure ? failure.status : undefined
  if (status === 404 || status === 405) {
    return `Prospero’s Study could not handle the connection test (POST /api/profiles/discover, HTTP ${status}). The running app server may be an older version. Close its server terminal, run launch.bat again, and refresh this page. This request did not reach your model provider.`
  }
  if (failure instanceof TypeError) {
    return 'The browser could not reach Prospero’s Study (POST /api/profiles/discover). Check that its server terminal is still running, then refresh this page. Your model provider has not been tested.'
  }
  if (failure instanceof SyntaxError) {
    return 'Prospero’s Study returned an unreadable response to POST /api/profiles/discover. Restart the app server and refresh this page, then retry. Check its terminal for details.'
  }
  return failure.message
}
