import { useId, useState, type FormEvent } from 'react'
import type { StockCategory, StockVariety, TagChoice } from '../api.ts'
import { Field, Problem } from '../forms.tsx'
import { useValues } from '../useValues.ts'
import { change, type StockTools } from './stockTools.ts'

// The forms on the stock page. Each one sends one change, then asks for the
// page again, so what's on screen is always what's in the database.

/** Dietary tags, as tick boxes (I2). */
function TagChecks({
  tags,
  chosen,
  onChange,
}: {
  tags: TagChoice[]
  chosen: number[]
  onChange: (chosen: number[]) => void
}) {
  if (tags.length === 0) return null
  return (
    <fieldset className="tag-checks">
      <legend>Tags</legend>
      {tags.map((tag) => (
        <label key={tag.id} className="check">
          <input
            type="checkbox"
            checked={chosen.includes(tag.id)}
            onChange={(event) =>
              onChange(event.target.checked ? [...chosen, tag.id] : chosen.filter((id) => id !== tag.id))
            }
          />
          {tag.name}
        </label>
      ))}
    </fieldset>
  )
}

/** A new kind of food, with its first variety: "Add food to book" or "Add an extra". */
export function AddFood({
  tools,
  categories,
  isExtra,
}: {
  tools: StockTools
  categories: StockCategory[]
  isExtra: boolean
}) {
  const [open, setOpen] = useState(false)
  const { values, set, clear } = useValues({ category_id: '', name: '', variety: '', on_shelf: '' })
  const [tagIds, setTagIds] = useState<number[]>([])
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const categoryBox = useId()
  const what = isExtra ? 'an extra' : 'food to book'

  if (!open) {
    return (
      <button type="button" className="secondary add-button" onClick={() => setOpen(true)}>
        + Add {what}
      </button>
    )
  }

  async function add(event: FormEvent) {
    event.preventDefault()
    if (values.category_id === '') {
      setProblem('Please fix the boxes marked in red.')
      return setFields({ category_id: 'Choose a category.' })
    }
    const answer = await change(tools, '/api/items', {
      category_id: Number(values.category_id),
      name: values.name,
      is_extra: isExtra,
      // An empty box is sent as -1, so the server's answer is "Type a number from 0 to 999."
      first_variety: { name: values.variety, tag_ids: tagIds, on_shelf: Number(values.on_shelf || -1) },
    })
    if (!answer.ok) {
      setProblem(answer.message)
      return setFields(answer.fields)
    }
    clear()
    setTagIds([])
    setProblem(null)
    setFields({})
    setOpen(false)
    tools.reload()
  }

  return (
    <form className="card add-form" onSubmit={add} noValidate autoComplete="off">
      <h3>Add {what}</h3>
      <Problem message={problem} />
      <div className={fields.category_id ? 'field field-wrong' : 'field'}>
        <label htmlFor={categoryBox}>Category</label>
        <select
          id={categoryBox}
          value={values.category_id}
          onChange={(event) => set('category_id')(event.target.value)}
        >
          <option value="">Choose one</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
        {fields.category_id && <p className="field-error">{fields.category_id}</p>}
      </div>
      <Field
        label="Item"
        hint="The kind of food, like Oats or Canned chicken. Already on the list? Use “Add a variety” under it."
        value={values.name}
        onChange={set('name')}
        error={fields.name}
        required
      />
      <Field
        label="Variety"
        hint="The exact kind, like Quick oats. If there's only one kind, type the item's name again."
        value={values.variety}
        onChange={set('variety')}
        error={fields['first_variety.name']}
        required
      />
      <TagChecks tags={tools.tags} chosen={tagIds} onChange={setTagIds} />
      <Field
        label="On the shelf now"
        type="number"
        inputMode="numeric"
        min={0}
        max={999}
        value={values.on_shelf}
        onChange={set('on_shelf')}
        error={fields['first_variety.on_shelf']}
        required
      />
      <p className="actions">
        <button type="submit">Add</button>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </p>
    </form>
  )
}

/** Another variety of an item already on the list, like Penne next to Spaghetti. */
export function AddVariety({ tools, itemId, itemName }: { tools: StockTools; itemId: number; itemName: string }) {
  const [open, setOpen] = useState(false)
  const { values, set, clear } = useValues({ name: '', on_shelf: '' })
  const [tagIds, setTagIds] = useState<number[]>([])
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})

  if (!open) {
    return (
      <button type="button" className="link-button" onClick={() => setOpen(true)}>
        + Add a variety of {itemName}
      </button>
    )
  }

  async function add(event: FormEvent) {
    event.preventDefault()
    const answer = await change(tools, `/api/items/${itemId}/varieties`, {
      name: values.name,
      tag_ids: tagIds,
      on_shelf: Number(values.on_shelf || -1), // empty: the server says what to type
    })
    if (!answer.ok) {
      setProblem(answer.message)
      return setFields(answer.fields)
    }
    clear()
    setTagIds([])
    setOpen(false)
    tools.reload()
  }

  return (
    <form className="inline-form" onSubmit={add} noValidate autoComplete="off">
      <Problem message={problem} />
      <Field label={`New variety of ${itemName}`} value={values.name} onChange={set('name')} error={fields.name} required />
      <TagChecks tags={tools.tags} chosen={tagIds} onChange={setTagIds} />
      <Field
        label="On the shelf now"
        type="number"
        inputMode="numeric"
        min={0}
        max={999}
        value={values.on_shelf}
        onChange={set('on_shelf')}
        error={fields.on_shelf}
        required
      />
      <p className="actions">
        <button type="submit">Add</button>
        <button type="button" className="secondary" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </p>
    </form>
  )
}

/** Tags, hide or show, and the name, of one variety. */
export function VarietyEditor({ tools, variety }: { tools: StockTools; variety: StockVariety }) {
  const [tagIds, setTagIds] = useState(variety.tag_ids)
  const [name, setName] = useState(variety.name)
  const [problem, setProblem] = useState<string | null>(null)

  async function run(path: string, body: object = {}, method: 'POST' | 'PUT' | 'PATCH' = 'POST') {
    const answer = await change(tools, path, body, method)
    if (!answer.ok) {
      return setProblem(answer.fields.name ?? answer.message)
    }
    setProblem(null)
    tools.reload()
  }

  return (
    <div className="editor">
      <Problem message={problem} />
      <TagChecks tags={tools.tags} chosen={tagIds} onChange={setTagIds} />
      <p className="actions">
        <button type="button" className="secondary" onClick={() => run(`/api/varieties/${variety.id}/tags`, { tag_ids: tagIds }, 'PUT')}>
          Save tags
        </button>
        {variety.shown ? (
          <button type="button" className="secondary" onClick={() => run(`/api/varieties/${variety.id}/hide`)}>
            Hide: we don't get this any more
          </button>
        ) : (
          <button type="button" className="secondary" onClick={() => run(`/api/varieties/${variety.id}/show`)}>
            Show again
          </button>
        )}
      </p>
      <form
        className="rename"
        onSubmit={(event) => {
          event.preventDefault()
          void run(`/api/varieties/${variety.id}`, { name }, 'PATCH')
        }}
      >
        <Field label="Fix the name" value={name} onChange={setName} />
        <button type="submit" className="secondary">
          Save name
        </button>
      </form>
    </div>
  )
}

/** Fix the name of an item or a category. Bookings show the new name, because they point to the row. */
export function Rename({ tools, path, current }: { tools: StockTools; path: string; current: string }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState(current)
  const [problem, setProblem] = useState<string | null>(null)

  if (!open) {
    return (
      <button type="button" className="link-button small" onClick={() => setOpen(true)}>
        Rename
      </button>
    )
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    const answer = await change(tools, path, { name }, 'PATCH')
    if (!answer.ok) return setProblem(answer.fields.name ?? answer.message)
    setOpen(false)
    tools.reload()
  }

  return (
    <form className="rename" onSubmit={save}>
      <Problem message={problem} />
      <Field label={`New name for ${current}`} value={name} onChange={setName} />
      <p className="actions">
        <button type="submit" className="secondary">
          Save name
        </button>
        <button type="button" className="link-button" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </p>
    </form>
  )
}

/** New categories and tags. Any staff member can add them (decided 7 Nov). */
export function CategoriesAndTags({ tools }: { tools: StockTools }) {
  return (
    <section className="card">
      <h2 className="in-card">Categories and tags</h2>
      <p className="muted">Check the list first, so there's only one of each.</p>
      <div className="two-forms">
        <AddName tools={tools} path="/api/categories" label="New category" example="like Snacks" />
        <AddName tools={tools} path="/api/tags" label="New tag" example="like Vegan" />
      </div>
      {tools.tags.length > 0 && (
        <p className="muted">Tags now: {tools.tags.map((tag) => tag.name).join(', ')}</p>
      )}
    </section>
  )
}

function AddName({ tools, path, label, example }: { tools: StockTools; path: string; label: string; example: string }) {
  const [name, setName] = useState('')
  const [problem, setProblem] = useState<string | null>(null)

  async function add(event: FormEvent) {
    event.preventDefault()
    const answer = await change(tools, path, { name })
    if (!answer.ok) return setProblem(answer.fields.name ?? answer.message)
    setName('')
    setProblem(null)
    tools.reload()
  }

  return (
    <form onSubmit={add} noValidate autoComplete="off">
      <Field label={label} hint={example} value={name} onChange={setName} error={problem ?? undefined} />
      <button type="submit" className="secondary">
        Add
      </button>
    </form>
  )
}
