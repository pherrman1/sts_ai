//
// Created by gamerpuppy on 7/4/2021.
//

#ifndef STS_LIGHTSPEED_ACTIONQUEUE_H
#define STS_LIGHTSPEED_ACTIONQUEUE_H

#include "sts_common.h"

#include <bitset>
#include <functional>
#include <cassert>


namespace sts {

    class BattleContext;
    typedef std::function<void (BattleContext &)> ActionFunction;

    struct Action {
        ActionFunction actFunc;
        bool clearOnCombatVictory = true;
        bool executeAfterCombatVictory = false;

        Action() = default;
        Action(ActionFunction a) : actFunc(std::move(a)) {}
        Action(ActionFunction a, bool b) : actFunc(std::move(a)), clearOnCombatVictory(b) {}
        Action(ActionFunction a, bool b, bool c)
            : actFunc(std::move(a)), clearOnCombatVictory(b), executeAfterCombatVictory(c) {}
    };


    // Simple deque
    template<int capacity>
    struct ActionQueue {
        friend BattleContext;
        int front = 0;
        int back = 0;
        int size = 0;
        std::bitset<capacity> bits; // for the shouldClear field
        std::bitset<capacity> postVictoryBits;

#ifdef sts_action_queue_use_raw_array
        ActionFunction arr[capacity];
        ActionQueue() = default;
        ActionQueue(const ActionQueue &rhs)
            : size(rhs.size), back(rhs.back), front(rhs.front), bits(rhs.bits),
              postVictoryBits(rhs.postVictoryBits) {
            int cur = rhs.front;
            for (int i = 0; i < rhs.size; ++i) {
                if (cur >= capacity) {
                    cur = 0;
                }
                arr[cur] = rhs.arr[cur];
            }
        }
#else
        std::array<ActionFunction,capacity> arr;
#endif

        void clear();
        void pushFront(Action a);
        void pushBack(Action a);
        bool isEmpty();
        bool hasPostVictoryAction() const;
        ActionFunction popPostVictoryAction();
        ActionFunction popFront();
        [[nodiscard]] int getCapacity() const;
    };

    template<int capacity>
    void ActionQueue<capacity>::clear() {
        size = 0;
        back = 0;
        front = 0;
        bits.reset();
        postVictoryBits.reset();
    }

    template <int capacity>
    void ActionQueue<capacity>::pushFront(Action a) {
#ifdef sts_asserts
        assert(size != capacity);
#endif
        --front;
        ++size;
        if (front < 0) {
            front = capacity-1;
        }
        bits.set(front, a.clearOnCombatVictory);
        postVictoryBits.set(front, a.executeAfterCombatVictory);
        arr[front] = std::move(a.actFunc);
    }

    template<int capacity>
    void ActionQueue<capacity>::pushBack(Action a) {
#ifdef sts_asserts
        if (size >= capacity) {
            assert(false);
        }
#endif
        if (back >= capacity) {
            back = 0;
        }
        bits.set(back, a.clearOnCombatVictory);
        postVictoryBits.set(back, a.executeAfterCombatVictory);
        arr[back] = std::move(a.actFunc);
        ++back;
        ++size;
    }

    template<int capacity>
    bool ActionQueue<capacity>::isEmpty() {
        return size == 0;
    }

    template<int capacity>
    bool ActionQueue<capacity>::hasPostVictoryAction() const {
        int cur = front;
        for (int i = 0; i < size; ++i) {
            if (cur >= capacity) {
                cur = 0;
            }
            if (postVictoryBits[cur]) {
                return true;
            }
            ++cur;
        }
        return false;
    }

    template<int capacity>
    ActionFunction ActionQueue<capacity>::popPostVictoryAction() {
        int cur = front;
        for (int i = 0; i < size; ++i) {
            if (cur >= capacity) {
                cur = 0;
            }
            if (postVictoryBits[cur]) {
                ActionFunction a = arr[cur];
                clear();
                return a;
            }
            ++cur;
        }
        return {};
    }

    template<int capacity>
    ActionFunction ActionQueue<capacity>::popFront() {
#ifdef sts_asserts
        assert(size > 0 );
#endif
        ActionFunction a = arr[front];
        ++front;
        --size;
        if (front >= capacity) {
            front = 0;
        }
        return a;
    }

    template<int capacity>
    int ActionQueue<capacity>::getCapacity() const {
        return capacity;
    }

}


#endif //STS_LIGHTSPEED_ACTIONQUEUE_H
