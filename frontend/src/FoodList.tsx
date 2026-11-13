import { useState } from 'react'
import { useServerData, type Category, type Food } from './api.ts'
import { FoodCard, FoodRow, StockNote } from './FoodCards.tsx'
import { countVarieties, filterFood, type Diet } from './foodFilter.ts'
import { DietFilters } from './ui/DietFilters.tsx'
import { Empty } from './ui/Empty.tsx'
import { Loading } from './ui/Loading.tsx'

/** What's on the shelf this week, as cards with a photo of each item. */
export function FoodList() {
  const food = useServerData<Food>('/api/food')
  const [diets, setDiets] = useState<Diet[]>([])

  if (food.state === 'loading') {
    return (
      <section>
        <h2>Food you can book</h2>
        <Loading shape="cards" label="Getting the food" />
      </section>
    )
  }
  if (food.state === 'failed') {
    return <p className="problem">Could not get the food list. Is the server running?</p>
  }

  return (
    <>
      <section>
        <h2>Food you can book</h2>
        <p className="muted">Choose up to 13 things when you book, one of each kind of food. Tap a card to see it bigger.</p>
        <DietFilters
          chosen={diets}
          onChange={setDiets}
          showing={countVarieties(filterFood(food.data.bookable, diets))}
          of={countVarieties(food.data.bookable)}
        />
        <FoodGrid
          categories={filterFood(food.data.bookable, diets)}
          empty={diets.length > 0 ? 'Nothing fits all of those. Try fewer filters.' : 'No food on the list yet.'}
          extras={false}
        />
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
  if (categories.length === 0) return <Empty icon="search" title={empty} />
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
                  ) : (
                    <StockNote stock={variety.stock} fewLeft={variety.few_left} />
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
