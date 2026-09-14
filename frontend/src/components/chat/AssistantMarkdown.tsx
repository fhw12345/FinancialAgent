/** Untrusted assistant Markdown boundary; preserve GFM but never load images. */
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function AssistantMarkdown({ children }: { children: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      disallowedElements={["img"]}
      components={{
        h1: ({ children }) => (
          <h1 className="text-xl font-bold mb-3 text-gray-900">{children}</h1>
        ),
        h2: ({ children }) => (
          <h2 className="text-lg font-bold mb-3 text-gray-900">{children}</h2>
        ),
        h3: ({ children }) => (
          <h3 className="text-base font-bold mb-2 text-gray-800">{children}</h3>
        ),
        p: ({ children }) => (
          <p className="mb-3 last:mb-0 leading-relaxed text-sm">{children}</p>
        ),
        ul: ({ children }) => (
          <ul className="list-disc list-inside mb-3 space-y-2 ml-2">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-inside mb-3 space-y-2 ml-2">
            {children}
          </ol>
        ),
        li: ({ children }) => (
          <li className="text-sm leading-relaxed">{children}</li>
        ),
        strong: ({ children }) => (
          <strong className="font-semibold text-gray-900">{children}</strong>
        ),
        a: ({ href, children }) => (
          <a
            className="text-blue-600 underline hover:text-blue-800"
            href={href}
            target="_blank"
            rel="noopener noreferrer"
          >
            {children}
          </a>
        ),
        code: ({ className, children, ...props }) => {
          const isInline = !className;
          return isInline ? (
            <code
              className="bg-blue-100 text-blue-800 px-1.5 py-0.5 rounded text-sm font-mono"
              {...props}
            >
              {children}
            </code>
          ) : (
            <code
              className={`block bg-gray-800 text-gray-100 p-3 rounded text-sm font-mono overflow-x-auto ${className}`}
              {...props}
            >
              {children}
            </code>
          );
        },
        pre: ({ children }) => (
          <pre className="mb-3 rounded overflow-hidden">{children}</pre>
        ),
        blockquote: ({ children }) => (
          <blockquote className="border-l-4 border-blue-500 pl-4 my-3 italic text-gray-700">
            {children}
          </blockquote>
        ),
        table: ({ children, style }) => (
          <div className="overflow-x-auto mb-3">
            <table
              style={style}
              className="min-w-full border-collapse border border-gray-300"
            >
              {children}
            </table>
          </div>
        ),
        thead: ({ children, style }) => (
          <thead style={style} className="bg-gray-100">
            {children}
          </thead>
        ),
        tbody: ({ children, style }) => <tbody style={style}>{children}</tbody>,
        tr: ({ children, style }) => (
          <tr style={style} className="border-b border-gray-300">
            {children}
          </tr>
        ),
        th: ({ children, style }) => (
          <th
            style={style}
            className="px-4 py-2 text-left font-semibold text-gray-900 border-r border-gray-300 last:border-r-0"
          >
            {children}
          </th>
        ),
        td: ({ children, style }) => (
          <td
            style={style}
            className="px-4 py-2 text-gray-800 border-r border-gray-300 last:border-r-0"
          >
            {children}
          </td>
        ),
        details: ({ children }) => (
          <details className="my-3 border border-gray-300 rounded-lg p-3 bg-gray-50">
            {children}
          </details>
        ),
        summary: ({ children }) => (
          <summary className="cursor-pointer font-medium text-blue-700 hover:text-blue-900 select-none">
            {children}
          </summary>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
