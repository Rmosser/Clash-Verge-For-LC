const openUrl = async (url: string) => { window.open(url, '_blank', 'noopener,noreferrer') }

export async function openExternalUrl(raw: string) {
  const url = new URL(raw.trim())

  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('Only HTTP and HTTPS URLs are allowed')
  }

  await openUrl(url.toString())
}
