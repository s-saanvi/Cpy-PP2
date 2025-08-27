# genetic_algorithm.py
import random
from collections import defaultdict
from models import ScheduledClass, Timeslot, FacultyPreference # Keep Timeslot for internal use

# Define constants for timetable structure
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
PERIODS_PER_DAY = 6 # Periods 1 through 6
TOTAL_PERIODS_PER_WEEK = PERIODS_PER_DAY * len(DAYS) # Used for normalization/scaling

# Slot definitions (for soft constraints and display)
SLOT_PERIODS = {
    1: [1, 2],
    2: [3, 4],
    3: [5, 6]
}
# Map period number to its slot (1, 2, or 3) for quick lookup
PERIOD_TO_SLOT = {p: s_num for s_num, periods in SLOT_PERIODS.items() for p in periods}

# --- Gene & Chromosome Representation ---

class TimetableChromosome:
    """Represents a single candidate timetable (an individual in GA).
    A chromosome is essentially a complete assignment of day/start_period
    for every ScheduledClass object that needs to be placed.
    """
    def __init__(self, scheduled_classes_with_assignments):
        # scheduled_classes_with_assignments: a list of ScheduledClass objects,
        # each with its 'day' and 'start_period' attributes already assigned by the GA.
        self.scheduled_classes = scheduled_classes_with_assignments
        self.fitness = 0.0 # To be calculated by the fitness function

    def __repr__(self):
        return f"TimetableChromosome(fitness={self.fitness})"

    def copy(self):
        """Creates a deep copy of the chromosome and its contained ScheduledClass objects.
        This is crucial for crossover and mutation to ensure we don't modify parents directly.
        """
        new_classes = []
        for sc in self.scheduled_classes:
            new_classes.append(sc.copy()) # Use the ScheduledClass.copy() method
        return TimetableChromosome(new_classes)

# --- Fitness Function ---

class TimetableFitness:
    """Calculates the fitness of a TimetableChromosome.
    Higher fitness values indicate a better timetable (fewer constraint violations).
    Hard constraints are heavily penalized; soft constraints less so.
    """
    def __init__(self, all_data):
        self.all_data = all_data
        self.faculty_preferences = all_data['faculty_preferences']

        # Pre-process faculty preferences for efficient lookup
        self.faculty_blocked_slots = defaultdict(set) # {faculty_id: {(day, period_num), ...}}
        self.faculty_preferred_slots = defaultdict(set) # {faculty_id: {(day, period_num), ...}}

        for pref in self.faculty_preferences:
            for p in range(pref.period_start, pref.period_end + 1):
                timeslot = (pref.day, p)
                if pref.preference_type == 'blocked':
                    self.faculty_blocked_slots[pref.faculty_id].add(timeslot)
                else: # 'preferred'
                    self.faculty_preferred_slots[pref.faculty_id].add(timeslot)

        # Base penalty values (can be tuned for desired behavior)
        # HARD CONSTRAINTS (High penalties to eliminate them first)
        self.PENALTY_HARD_COLLISION = 1000 # Very high for any resource conflict
        self.PENALTY_HARD_FACULTY_BLOCKED = 500 # Ensure faculty are not scheduled during blocked times
        self.PENALTY_HARD_LAB_CONTINUITY_INVALID = 500 # If lab somehow gets non-2-hour or invalid end
        self.PENALTY_HARD_THEORY_PERIOD_LIMIT = 750 # For theory classes assigned beyond period 4

        # SOFT CONSTRAINTS (Lower penalties, for optimization after hard constraints are met)
        self.PENALTY_SOFT_FACULTY_PREFERRED_NOT_MET = 10 # Encourage preferred times, but not strictly required
        self.PENALTY_SOFT_LAB_CROSSING_BREAK = 5 # Discourage labs spanning recess/lunch
        self.PENALTY_SOFT_SEMESTER_SCATTER = 2 # Penalize gaps within a semester's day schedule
        self.PENALTY_SOFT_FACULTY_SCATTER = 3 # Penalize gaps within a faculty's day schedule
        self.PENALTY_SOFT_SINGLE_CLASS_DAY = 15 # Penalize faculty teaching only one class on a day

    def calculate(self, chromosome: TimetableChromosome):
        total_penalties = 0

        # Maps to keep track of occupied slots for hard constraint checks
        # Format: {ID: {(day, period_num), ...}}
        semester_occupied_slots = defaultdict(set)
        faculty_occupied_slots = defaultdict(set)

        # For compactness (soft constraint S3, S4)
        # {semester_id: {day: {periods: [p1,p2,...], total_hours: X}}}
        semester_day_schedule = defaultdict(lambda: defaultdict(lambda: {'periods': [], 'total_hours': 0}))
        # {faculty_id: {day: {periods: [p1,p2,...], total_hours: X}}}
        faculty_day_schedule = defaultdict(lambda: defaultdict(lambda: {'periods': [], 'total_hours': 0}))


        for scheduled_class in chromosome.scheduled_classes:
            # Check if class is placed (it should be after GA mutation/creation)
            if scheduled_class.day is None or scheduled_class.start_period is None:
                total_penalties += self.PENALTY_HARD_COLLISION # Treat unplaced as a major issue
                continue

            # Get all 1-hour timeslots occupied by this class
            occupied_timeslots_by_class = []
            for p in range(scheduled_class.start_period, scheduled_class.end_period + 1):
                occupied_timeslots_by_class.append((scheduled_class.day, p))

            # --- HARD CONSTRAINTS ---

            # H1: No Overlapping Classes for a Semester
            for ts in occupied_timeslots_by_class:
                if ts in semester_occupied_slots[scheduled_class.semester_id]:
                    total_penalties += self.PENALTY_HARD_COLLISION
                    break # No need to check other periods for this class if collision found
                semester_occupied_slots[scheduled_class.semester_id].add(ts)

            # H2: No Overlapping Classes for a Faculty
            for faculty_id in scheduled_class.faculty_ids:
                for ts in occupied_timeslots_by_class:
                    if ts in faculty_occupied_slots[faculty_id]:
                        total_penalties += self.PENALTY_HARD_COLLISION
                        break # No need to check other periods for this class if collision found
                    faculty_occupied_slots[faculty_id].add(ts)

            # H3: Faculty Blocked Hours
            for faculty_id in scheduled_class.faculty_ids:
                for ts in occupied_timeslots_by_class:
                    if ts in self.faculty_blocked_slots[faculty_id]:
                        total_penalties += self.PENALTY_HARD_FACULTY_BLOCKED
                        break # Penalty already applied for this faculty for this class

            # H4: Lab Continuity & Validity (Should be mostly handled at creation, but check) _and_ Theory Period Limit
            if scheduled_class.is_lab:
                if scheduled_class.periods_count != 2:
                    total_penalties += self.PENALTY_HARD_LAB_CONTINUITY_INVALID # Lab must be 2 periods
                # Check if lab extends beyond day's periods (e.g., starts at P6)
                if scheduled_class.end_period > PERIODS_PER_DAY:
                    total_penalties += self.PENALTY_HARD_LAB_CONTINUITY_INVALID
                # Check if 2-period lab is consecutive (e.g. starts P1, periods 1 & 2 only)
                if scheduled_class.periods_count > 1 and scheduled_class.end_period - scheduled_class.start_period + 1 != scheduled_class.periods_count:
                    total_penalties += self.PENALTY_HARD_LAB_CONTINUITY_INVALID
            else: # It's a theory class
                # H5: Theory courses must be assigned within the first 4 periods.
                if scheduled_class.end_period > 4: # If any part of the theory class extends beyond P4
                    total_penalties += self.PENALTY_HARD_THEORY_PERIOD_LIMIT

            # --- SOFT CONSTRAINTS ---

            # S1: Faculty Preferred Hours
            for faculty_id in scheduled_class.faculty_ids:
                is_preferred_met_for_all_periods = True
                for ts in occupied_timeslots_by_class:
                    if ts not in self.faculty_preferred_slots[faculty_id]:
                        is_preferred_met_for_all_periods = False
                        break
                if not is_preferred_met_for_all_periods:
                    total_penalties += self.PENALTY_SOFT_FACULTY_PREFERRED_NOT_MET
                    # Note: If it IS in a preferred slot, no penalty. No bonus system for now.

            # S2: Lab Crossing Breaks (P2-P3 crosses recess, P4-P5 crosses lunch)
            if scheduled_class.is_lab and scheduled_class.periods_count == 2:
                # Breaks are after P2 (Recess) and after P4 (Lunch)
                if scheduled_class.start_period == 2 or scheduled_class.start_period == 4:
                    total_penalties += self.PENALTY_SOFT_LAB_CROSSING_BREAK
            
            # For S3, S4, and S5: Populate schedule maps
            for p in range(scheduled_class.start_period, scheduled_class.end_period + 1):
                semester_day_schedule[scheduled_class.semester_id][scheduled_class.day]['periods'].append(p)
                semester_day_schedule[scheduled_class.semester_id][scheduled_class.day]['total_hours'] += 1
                for faculty_id in scheduled_class.faculty_ids:
                    faculty_day_schedule[faculty_id][scheduled_class.day]['periods'].append(p)
                    faculty_day_schedule[faculty_id][scheduled_class.day]['total_hours'] += 1

        # S3: Semester timetable compactness
        for sem_id, days_data in semester_day_schedule.items():
            for day, schedule_data in days_data.items():
                periods = sorted(list(set(schedule_data['periods']))) # Unique & sorted periods
                total_hours_scheduled = schedule_data['total_hours']
                if periods:
                    min_period = periods[0]
                    max_period = periods[-1]
                    span = max_period - min_period + 1
                    gaps = span - total_hours_scheduled
                    if gaps > 0:
                        total_penalties += gaps * self.PENALTY_SOFT_SEMESTER_SCATTER

        # S4: Faculty timetable compactness
        # S5: Single class day penalty for faculty
        for fac_id, days_data in faculty_day_schedule.items():
            for day, schedule_data in days_data.items():
                periods = sorted(list(set(schedule_data['periods']))) # Unique & sorted periods
                total_hours_scheduled = schedule_data['total_hours']
                if periods:
                    min_period = periods[0]
                    max_period = periods[-1]
                    span = max_period - min_period + 1
                    gaps = span - total_hours_scheduled
                    if gaps > 0:
                        total_penalties += gaps * self.PENALTY_SOFT_FACULTY_SCATTER
                    
                    # S5: Single Class Day Penalty
                    if total_hours_scheduled == 1:
                        total_penalties += self.PENALTY_SOFT_SINGLE_CLASS_DAY


        # The fitness score is calculated by minimizing penalties.
        chromosome.fitness = -total_penalties
        return chromosome.fitness

# --- Genetic Algorithm Core Logic ---

class GeneticAlgorithm:
    def __init__(self, classes_to_schedule, all_data, population_size=100, generations=500,
                 mutation_chance_smart=0.8, mutation_rate=0.05, crossover_rate=0.8):
        """
        Initializes the Genetic Algorithm.
        :param mutation_chance_smart: Probability that mutation attempts a "smart" placement.
        """
        self.classes_to_schedule_template = classes_to_schedule
        self.all_data = all_data
        self.population_size = population_size
        self.generations = generations
        self.mutation_rate = mutation_rate # Per gene mutation probability
        self.mutation_chance_smart = mutation_chance_smart # Chromosome-level choice for mutation strategy
        self.crossover_rate = crossover_rate

        self.fitness_calculator = TimetableFitness(all_data)

        if not self.classes_to_schedule_template:
            raise ValueError("No classes to schedule found. Please add courses and mappings.")
        if not self.all_data['semesters']:
            raise ValueError("No semesters defined in the database.")
        if not self.all_data['faculty']:
            raise ValueError("No faculty defined in the database.")

        self.days = DAYS
        self.periods_per_day = PERIODS_PER_DAY

    def _get_random_timeslot(self, periods_count, is_lab):
        """Helper to get a random valid start time (day and period) for a class
        given its duration (periods_count) and type (is_lab).
        Ensures the class fits within the day and adheres to theory period limit.
        """
        day = random.choice(self.days)
        
        if not is_lab: # It's a theory class, restricted to periods 1-4
            # Max period a theory class can *end* at is 4.
            # So, if a theory class is 1 hour, it can start at 1, 2, 3, or 4.
            # If a theory class is 2 hours, it can start at 1, 2, 3.
            max_end_period_for_theory = 4
            max_start_period_for_theory = max_end_period_for_theory - periods_count + 1
            
            if periods_count > max_end_period_for_theory:
                 raise ValueError(f"Theory class periods_count ({periods_count}) exceeds the maximum allowed periods ({max_end_period_for_theory}). Theory classes cannot be longer than {max_end_period_for_theory} hours for this constraint.")

            if max_start_period_for_theory < 1:
                # This check ensures that even for P_cnt=4, max_start_period is 1.
                raise ValueError(f"Calculated max_start_period_for_theory ({max_start_period_for_theory}) is less than 1. Check periods_count for theory class.")
            
            start_period = random.randint(1, max_start_period_for_theory)
        else: # It's a lab class, can use all 6 periods
            max_start_period_for_lab = self.periods_per_day - periods_count + 1
            if max_start_period_for_lab < 1:
                raise ValueError(f"Periods count ({periods_count}) exceeds periods per day ({self.periods_per_day}) for lab class.")
            start_period = random.randint(1, max_start_period_for_lab)
        
        return day, start_period
    
    def _attempt_find_empty_slot(self, class_to_place: ScheduledClass, current_chromosome: TimetableChromosome, max_attempts=50):
        """
        Attempts to find an empty slot for a given class that does not cause hard collisions.
        This is a greedy approach for mutation.
        """
        # Simulate current occupied slots based on the chromosome
        temp_semester_occupied_slots = defaultdict(set)
        temp_faculty_occupied_slots = defaultdict(set)

        # Populate temporary occupied slots, EXCLUDING the class_to_place itself
        # This is because we are trying to re-place class_to_place
        for sc in current_chromosome.scheduled_classes:
            if sc is class_to_place: continue # Skip the class we are trying to re-place

            if sc.day is not None and sc.start_period is not None:
                for p in range(sc.start_period, sc.end_period + 1):
                    temp_semester_occupied_slots[sc.semester_id].add((sc.day, p))
                    for fac_id in sc.faculty_ids:
                        temp_faculty_occupied_slots[fac_id].add((sc.day, p))
        
        possible_slots = []
        # Iterate all possible timeslots and filter for validity
        for day in self.days:
            # Determine maximum period based on class type
            max_end_period_for_type = 4 if not class_to_place.is_lab else self.periods_per_day
            
            # Iterate through possible start periods
            for start_p_candidate in range(1, max_end_period_for_type - class_to_place.periods_count + 2): # +2 for 1-based start, and inclusive end period
            
                is_valid = True
                
                # Check if it fits within the allowed period range for its type
                if start_p_candidate + class_to_place.periods_count - 1 > max_end_period_for_type:
                    is_valid = False
                    
                if is_valid: # Basic day/type fit check
                    # Check for collisions with other classes and blocked times
                    for p_offset in range(class_to_place.periods_count):
                        period = start_p_candidate + p_offset
                        timeslot = (day, period)

                        # Semester collision check
                        if timeslot in temp_semester_occupied_slots[class_to_place.semester_id]:
                            is_valid = False
                            break
                        
                        # Faculty collision check & Blocked Time check
                        for fac_id in class_to_place.faculty_ids:
                            if timeslot in temp_faculty_occupied_slots[fac_id]:
                                is_valid = False
                                break
                            if timeslot in self.fitness_calculator.faculty_blocked_slots[fac_id]:
                                is_valid = False
                                break
                        if not is_valid: break # Break from periods loop if collision/blocked found

                if is_valid:
                    possible_slots.append((day, start_p_candidate))

        random.shuffle(possible_slots) # Shuffle to add randomness to "smart" mutation

        for day, start_period in possible_slots:
            return day, start_period
        
        return None, None # No empty slot found

    def create_individual(self):
        """Generates a single random timetable (chromosome)."""
        new_scheduled_classes = []
        for class_item_template in self.classes_to_schedule_template:
            scheduled_copy = class_item_template.copy()
            
            # Pass is_lab to _get_random_timeslot
            day, start_period = self._get_random_timeslot(scheduled_copy.periods_count, scheduled_copy.is_lab)
            scheduled_copy.day = day
            scheduled_copy.start_period = start_period
            new_scheduled_classes.append(scheduled_copy)

        return TimetableChromosome(new_scheduled_classes)

    def initialize_population(self):
        """Creates the initial population of chromosomes."""
        population = []
        for _ in range(self.population_size):
            individual = self.create_individual()
            self.fitness_calculator.calculate(individual) # Calculate initial fitness
            population.append(individual)
        return population

    def selection(self, population):
        """Tournament selection: selects the fittest individuals for reproduction."""
        selected_parents = []
        tournament_size = 5
        for _ in range(self.population_size):
            tournament_competitors = random.sample(population, tournament_size)
            winner = max(tournament_competitors, key=lambda x: x.fitness)
            selected_parents.append(winner)
        return selected_parents

    def crossover(self, parent1: TimetableChromosome, parent2: TimetableChromosome):
        """Performs one-point crossover between two parent chromosomes."""
        if random.random() < self.crossover_rate:
            child1 = parent1.copy()
            child2 = parent2.copy()

            crossover_point = random.randint(1, len(self.classes_to_schedule_template) - 1)

            for i in range(crossover_point, len(self.classes_to_schedule_template)):
                # Inherit position from parents. Fitness function will penalize invalid positions.
                child1.scheduled_classes[i].day = parent2.scheduled_classes[i].day
                child1.scheduled_classes[i].start_period = parent2.scheduled_classes[i].start_period

                child2.scheduled_classes[i].day = parent1.scheduled_classes[i].day
                child2.scheduled_classes[i].start_period = parent1.scheduled_classes[i].start_period

            return child1, child2
        else:
            return parent1.copy(), parent2.copy()

    def mutation(self, chromosome: TimetableChromosome):
        """Mutates a chromosome by randomly changing the day and/or start_period
        of a few scheduled classes (genes). Incorporates a 'smarter' mutation strategy.
        """
        perform_smart_mutation = random.random() < self.mutation_chance_smart

        for scheduled_class in chromosome.scheduled_classes:
            if random.random() < self.mutation_rate: # Check if this gene should mutate
                # Try smarter mutation first
                if perform_smart_mutation:
                    new_day, new_start_period = self._attempt_find_empty_slot(scheduled_class, chromosome)
                    if new_day is not None:
                        scheduled_class.day = new_day
                        scheduled_class.start_period = new_start_period
                    else: # Fallback to random if smart mutation failed to find an empty slot
                        # Fallback uses _get_random_timeslot, respecting is_lab
                        day, start_period = self._get_random_timeslot(scheduled_class.periods_count, scheduled_class.is_lab)
                        scheduled_class.day = day
                        scheduled_class.start_period = start_period
                else: # Purely random mutation (but still guided by _get_random_timeslot)
                    day, start_period = self._get_random_timeslot(scheduled_class.periods_count, scheduled_class.is_lab)
                    scheduled_class.day = day
                    scheduled_class.start_period = start_period

    def run(self, progress_callback=None):
        """
        Runs the main Genetic Algorithm loop.
        """
        population = self.initialize_population()
        best_individual = max(population, key=lambda x: x.fitness)

        for gen in range(self.generations):
            # Ensure fitness is up-to-date for selection
            for individual in population:
                self.fitness_calculator.calculate(individual)

            current_best_in_generation = max(population, key=lambda x: x.fitness)
            if current_best_in_generation.fitness > best_individual.fitness:
                best_individual = current_best_in_generation.copy()

            selected_parents = self.selection(population)

            next_population = []
            random.shuffle(selected_parents) # Shuffle to pair parents randomly
            
            for i in range(0, len(selected_parents), 2):
                p1 = selected_parents[i]
                p2 = selected_parents[i+1] if i+1 < len(selected_parents) else random.choice(selected_parents) # Handle odd number of parents

                child1, child2 = self.crossover(p1, p2)

                self.mutation(child1)
                self.mutation(child2)

                self.fitness_calculator.calculate(child1)
                self.fitness_calculator.calculate(child2)

                next_population.append(child1)
                if len(next_population) < self.population_size:
                    next_population.append(child2)
            
            population = next_population # Replace old population with the new generation

            if progress_callback:
                progress_callback(gen + 1, self.generations, best_individual.fitness)

            # Early stopping if an "optimal" solution (no hard violations) is found
            if best_individual.fitness >= 0:
                print(f"Optimal fitness (no hard constraints violated) reached at generation {gen+1}!")
                break
        
        self.fitness_calculator.calculate(best_individual) # Final calculation for the returned best individual
        return best_individual
