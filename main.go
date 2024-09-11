//  This file is part of ilo4_unlock (https://github.com/kendallgoto/ilo4_unlock/).
//  Copyright (c) 2024 Kendall Goto.
//
//  This program is free software: you can redistribute it and/or modify
//  it under the terms of the GNU General Public License as published by
//  the Free Software Foundation, version 3.
//
//  This program is distributed in the hope that it will be useful, but
//  WITHOUT ANY WARRANTY; without even the implied warranty of
//  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
//  General Public License for more details.
//
//  You should have received a copy of the GNU General Public License
//  along with this program. If not, see <http://www.gnu.org/licenses/>.

package main

import (
	"log"
	"os"

	"embed"

	"github.com/kendallgoto/ilo4_unlock/cmd/patch"
	"github.com/kendallgoto/ilo4_unlock/cmd/setup"
	"github.com/kendallgoto/ilo4_unlock/pkg/config"
	"github.com/urfave/cli/v2"
)

//go:embed patches/*/patch.yml
//go:embed patches/config.yml
var EmbeddedConfig embed.FS

func main() {
	patchBase := patch.Command()
	app := &cli.App{
		Name:  "ilo4_unlock",
		Usage: "tools for freeing iLO for homelabs",
		Flags: []cli.Flag{
			&cli.StringFlag{
				Name:  "workdir",
				Usage: "working directory path",
				Value: "build/",
			},
			&cli.StringSliceFlag{
				Name:  "patches",
				Usage: "additional patches to include (e.g. \"patches/abc\")",
			},
		},
		Commands: []*cli.Command{
			setup.Command(),
			patchBase,
		},
		Before: func(cCtx *cli.Context) error {
			err := config.BuildConfig(EmbeddedConfig, cCtx.StringSlice("patches"))
			if err != nil {
				return err
			}
			patch.AddPatchCommands(patchBase)
			return nil
		},
	}
	if err := app.Run(os.Args); err != nil {
		log.Fatal(err)
	}
}
