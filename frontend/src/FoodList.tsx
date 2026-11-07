import { useServerData, type Category, type Food } from './api.ts'
import { FoodCard, FoodRow } from './FoodCards.tsx'

/** What's on the shelf this week, as cards with a photo of each item. */
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
        <h2>Food you can book</h2>
        <p className="muted">Choose up to 13 things when you book, one of each kind of food.</p>
        <FoodGrid categories={food.data.bookable} empty="No food on the list yet." extras={false} />
      </section>
      <section>
        <h2>Extras</h2>
        <p className="muted">Not booked online. They may be available: ask at pickup, one of each.</p>
        <FoodGrid categories={food.data.extras} empty="No extras today." extras />
      </section>
    </>
  )
}

function FoodGrid({ categories, empty, extras }: { categories: Category[]; empty: string; extras: boolean }) {
  if (categories.length === 0) return <p className="muted">{empty}</p>
  return (
    <div className="food-grid">
      {categories.flatMap((category) =>
        category.items.map((item) => (
          <FoodCard key={item.id} name={item.name} category={category.name} photoUrl={item.photo_url}>
            {item.varieties.map((variety) => (
              <FoodRow
                key={variety.id}
                name={variety.name}
                tags={variety.tags}
                dim={variety.stock === 0}
                note={
                  extras ? (
                    'May be available'
                  ) : variety.stock === 0 ? (
                    <span className="stock-out">Out of stock</span>
                  ) : (
                    <span className="stock-left">{variety.stock} left</span>
                  )
                }
              />
            ))}
          </FoodCard>
        )),
      )}
    </div>
  )
}
