export const dismissDialogsEvent = 'prospero:dismiss-dialogs'
export function dismissWorkspaceDialogs() { window.dispatchEvent(new Event(dismissDialogsEvent)) }
