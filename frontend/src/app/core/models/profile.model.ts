export interface Skill {
  name: string;
  rating: number;
}

export interface Project {
  name: string;
  repository_link: string;
  summary: string;
  date_from: string;
  date_to: string;
  tech_stack: string[];
}

export interface Experience {
  title: string;
  company: string;
  description: string;
  date_from: string;
  date_to: string;
  tech_stack: string[];
}

export interface UserProfile {
  summary: string;
  skills: Skill[];
  projects: Project[];
  experience: Experience[];
}

export interface MatchedOffer {
  link: string;
  title: string;
  company: string;
  score: number;
  matched_skills: string[];
}
