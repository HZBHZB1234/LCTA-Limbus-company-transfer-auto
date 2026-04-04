import { marked } from 'marked'

// 自定义渲染器：使链接在新标签页打开
const renderer = new marked.Renderer()
renderer.link = function(href, title, text) {
  const link = marked.Renderer.prototype.link.call(this, href, title, text)
  return link.replace('<a', '<a target="_blank" rel="noopener noreferrer"')
}

marked.setOptions({ renderer })

export function renderMarkdown(text) {
  if (!text) return ''
  return marked.parse(text)
}

export async function loadMarkdown(url) {
  try {
    const response = await fetch(url)
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    const text = await response.text()
    return renderMarkdown(text)
  } catch (error) {
    console.error(`加载 Markdown 失败: ${url}`, error)
    return `<p class="error">加载内容失败: ${error.message}</p>`
  }
}