import { useServerData, type Category, type Food, type Variety } from './api.ts'

export function FoodList() {
  const food = useServerData<Food>('/api/food')

  if (food.state === 'loading') {
    return <p className="muted">Asking the server...</p>
  }
  if (food.state === 'failed') {
    return <p className="problem">Could not get the food list. Is the server running?</p>
  }

  return (
    <>
      <section>
        <h2>Food to book</h2>
        <CategoryList categories={food.data.bookable} empty="No food on the list yet." />
      </section>
      <section>
        <h2>Extras</h2>
        <p className="muted">Not booked online. They may be available: ask at pickup.</p>
        <CategoryList categories={food.data.extras} empty="No extras on the list." />
      </section>
    </>
  )
}

function CategoryList({ categories, empty }: { categories: Category[]; empty: string }) {
  if (categories.length === 0) {
    return <p className="muted">{empty}</p>
  }
  return (
    <div className="categories">
      {categories.map((category) => (
        <article key={category.name} className="card">
          <h3>{category.name}</h3>
          {category.items.map((item) => (
            <div key={item.name} className="item">
              <h4>{item.name}</h4>
              <ul className="varieties">
                {item.varieties.map((variety) => (
                  <VarietyRow key={variety.name} variety={variety} />
                ))}
              </ul>
            </div>
          ))}
        </article>
      ))}
    </div>
  )
}

function VarietyRow({ variety }: { variety: Variety }) {
  return (
    <li className={variety.stock === 0 ? 'variety variety-out' : 'variety'}>
      <span className="variety-name">{variety.name}</span>
      {variety.tags.map((tag) => (
        <span key={tag} className="tag">
          {tag}
        </span>
      ))}
      <span className="stock">{stockText(variety.stock)}</span>
    </li>
  )
}

function stockText(stock: number | null): string {
  if (stock === null) return 'May be available'
  if (stock === 0) return 'Out of stock'
  return `${stock} left`
}
